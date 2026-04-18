import json
from pathlib import Path

import httpx
import streamlit as st
from PIL import Image

import streamlit.elements.image as _st_image
if not hasattr(_st_image, "image_to_url"):
    from streamlit.elements.lib.image_utils import image_to_url as _new_image_to_url
    from streamlit.elements.lib.layout_utils import LayoutConfig as _LayoutConfig

    def _image_to_url_shim(image, width, clamp, channels, output_format, image_id):
        return _new_image_to_url(
            image, _LayoutConfig(width=width),
            clamp, channels, output_format, image_id,
        )

    _st_image.image_to_url = _image_to_url_shim

from streamlit_drawable_canvas import st_canvas

from admin_ui.api import get_template, update_template

st.set_page_config(page_title="Annotate", layout="wide")
st.title("Annotate template zones")


def _err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"API {e.response.status_code}: {e.response.text}"
    return f"API error: {e}"


sel = st.session_state.get("selected_template_id")
tid = st.number_input("Template ID", min_value=1, step=1,
                       value=int(sel) if sel else 1)
tid = int(tid)

try:
    tpl = get_template(tid)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        st.info(f"No template #{tid}. Enter a valid ID above.")
        st.stop()
    st.error(_err(e))
    st.stop()
except Exception as e:
    st.error(_err(e))
    st.stop()

st.caption(f"**{tpl['name']}** · `{tpl['doc_type_code']}` v{tpl['version']} · "
           f"{'✅ active' if tpl['is_active'] else '⛔ inactive'}")

if not tpl["pages"]:
    st.warning("No pages uploaded. Add a sample image on the Templates page first.")
    st.stop()

page_opts = {f"page {p['page_index']} ({p['image_width']}×{p['image_height']})":
             p for p in tpl["pages"]}
pick = st.selectbox("Page", list(page_opts.keys()))
page = page_opts[pick]

img_path = Path(page["image_path"])
if not img_path.exists():
    st.error(f"Image file missing on disk: {img_path}")
    st.stop()

try:
    pil_img = Image.open(img_path).convert("RGB")
except Exception as e:
    st.error(f"Cannot open image: {e}")
    st.stop()

native_w = page["image_width"]
native_h = page["image_height"]
MAX_W = 900
scale = min(1.0, MAX_W / native_w)
disp_w = int(native_w * scale)
disp_h = int(native_h * scale)

st.caption(f"Draw rectangles over zones. Display scale: {scale:.2f} "
           f"(coords auto-converted to native {native_w}×{native_h}).")

draft_key = f"draft_fields_{tid}"
if draft_key not in st.session_state:
    st.session_state[draft_key] = [
        {"name": f["name"], "page_index": f["page_index"],
         "strategy": f["strategy"], "config": f["config"],
         "post_process": f["post_process"], "required": f["required"],
         "display_order": f["display_order"]}
        for f in tpl["fields"]
    ]

col_canvas, col_form = st.columns([3, 2])

with col_canvas:
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.2)",
        stroke_width=2,
        stroke_color="#FF0000",
        background_image=pil_img,
        update_streamlit=True,
        height=disp_h,
        width=disp_w,
        drawing_mode="rect",
        key=f"canvas_{tid}_{page['page_index']}",
    )

with col_form:
    st.subheader("Convert last rect → field")
    rects = []
    if canvas_result.json_data and canvas_result.json_data.get("objects"):
        rects = [o for o in canvas_result.json_data["objects"]
                 if o.get("type") == "rect"]
    if not rects:
        st.info("Draw a rectangle on the left to capture a zone.")
    else:
        last = rects[-1]
        x = int(last["left"] / scale)
        y = int(last["top"] / scale)
        w = int(last["width"] * last.get("scaleX", 1) / scale)
        h = int(last["height"] * last.get("scaleY", 1) / scale)
        st.code(f"native coords: x={x}  y={y}  w={w}  h={h}")
        with st.form(f"addfield_{tid}_{len(rects)}"):
            fname = st.text_input("Field name")
            post = st.selectbox("post_process",
                                 ["(none)", "trim", "uppercase", "lowercase",
                                  "number", "date"], index=1)
            required = st.checkbox("Required", value=False)
            merge = st.checkbox("Merge multi-line in zone", value=True)
            order = st.number_input("display_order", min_value=0, value=1, step=1)
            if st.form_submit_button("Add zone field", type="primary"):
                if not fname.strip():
                    st.error("Field name required.")
                else:
                    st.session_state[draft_key].append({
                        "name": fname.strip(),
                        "page_index": page["page_index"],
                        "strategy": "zone",
                        "config": {"x": x, "y": y, "w": w, "h": h, "merge": merge},
                        "post_process": None if post == "(none)" else post,
                        "required": required,
                        "display_order": int(order),
                    })
                    st.success(f"Added field '{fname}'.")
                    st.rerun()

st.divider()
st.subheader("Draft fields")
draft = st.session_state[draft_key]
if not draft:
    st.info("No fields yet.")
else:
    for i, f in enumerate(draft):
        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
        c1.markdown(f"**{f['name']}** · page {f['page_index']} · "
                    f"{f['strategy']} · post={f['post_process']}")
        c2.caption(json.dumps(f["config"]))
        c3.caption(f"ord={f['display_order']}{' · req' if f['required'] else ''}")
        if c4.button("✕", key=f"rm_{i}_{f['name']}"):
            st.session_state[draft_key].pop(i)
            st.rerun()

st.divider()
edited_raw = st.text_area("Edit raw JSON (optional)",
                           value=json.dumps(draft, indent=2), height=260,
                           key=f"raw_{tid}")
c_apply, c_save = st.columns(2)
if c_apply.button("Apply JSON to draft"):
    try:
        parsed = json.loads(edited_raw)
        st.session_state[draft_key] = parsed
        st.success("Draft updated.")
        st.rerun()
    except Exception as e:
        st.error(f"Invalid JSON: {e}")
if c_save.button("Save as NEW version", type="primary"):
    try:
        new = update_template(tid, None, st.session_state[draft_key])
        st.success(f"Saved template #{new['id']} v{new['version']}")
        st.session_state["selected_template_id"] = new["id"]
        st.session_state.pop(draft_key, None)
        st.rerun()
    except Exception as e:
        st.error(_err(e))
