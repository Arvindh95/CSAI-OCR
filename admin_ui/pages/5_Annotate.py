import json
from pathlib import Path

import httpx
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

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
import streamlit.components.v1 as components

from admin_ui.api import get_page_lines, get_template, update_template


def _overlap_ratio(line_bbox, zone):
    lx, ly, lw, lh = line_bbox
    zx1, zy1, zx2, zy2 = zone
    ix1 = max(lx, zx1)
    iy1 = max(ly, zy1)
    ix2 = min(lx + lw, zx2)
    iy2 = min(ly + lh, zy2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    line_area = max(lw * lh, 1)
    return inter / line_area

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
scale = 1.0
disp_w = native_w
disp_h = native_h

st.markdown(
    f"""
    <style>
    div[data-testid="stVerticalBlockBorderWrapper"]:has(iframe[title*="drawable_canvas" i]) {{
        overflow: auto !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(iframe[title*="drawable_canvas" i]) iframe {{
        width: {disp_w}px !important;
        min-width: {disp_w}px !important;
        max-width: none !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.caption(f"Native {native_w}×{native_h}. Middle-click + drag to pan. "
           "Scrollbars also available.")

lines_key = f"lines_{tid}_{page['page_index']}"
c_fetch, c_status = st.columns([1, 3])
if c_fetch.button("Load OCR lines (preview)"):
    try:
        with st.spinner("Running OCR on page..."):
            res = get_page_lines(tid, page["page_index"])
        st.session_state[lines_key] = res.get("lines", [])
        st.success(f"Loaded {len(st.session_state[lines_key])} lines.")
    except Exception as e:
        st.error(_err(e))
cached_lines = st.session_state.get(lines_key)
if cached_lines is not None:
    c_status.caption(f"📄 {len(cached_lines)} OCR lines cached · "
                     "preview active below canvas")
else:
    c_status.caption("No OCR lines loaded. Click ← to enable live preview.")

draft_key = f"draft_fields_{tid}"
if draft_key not in st.session_state:
    st.session_state[draft_key] = [
        {"name": f["name"], "page_index": f["page_index"],
         "strategy": f["strategy"], "config": f["config"],
         "post_process": f["post_process"], "required": f["required"],
         "display_order": f["display_order"]}
        for f in tpl["fields"]
    ]

c_ov1, c_ov2 = st.columns(2)
show_existing = c_ov1.checkbox("Show existing draft zones",
                                value=True,
                                key=f"showex_{tid}_{page['page_index']}")
show_lines = c_ov2.checkbox("Show OCR line boxes",
                             value=True,
                             key=f"showln_{tid}_{page['page_index']}",
                             help="Green boxes show exact OCR line bounds. "
                                  "Draw zones tight around them for best match. "
                                  "Load OCR lines first.")
bg_img = pil_img
need_overlay = show_existing or (show_lines and cached_lines)
if need_overlay:
    overlay = pil_img.copy()
    draw = ImageDraw.Draw(overlay, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    if show_lines and cached_lines:
        for ln in cached_lines:
            if "bbox" not in ln:
                continue
            bx, by, bw, bh = ln["bbox"]
            draw.rectangle([bx, by, bx + bw, by + bh],
                            outline=(0, 200, 80, 220), width=1,
                            fill=(0, 200, 80, 25))
    if show_existing:
        for f in st.session_state[draft_key]:
            if f.get("strategy") != "zone" or f.get("page_index") != page["page_index"]:
                continue
            cfg = f.get("config", {})
            try:
                zx = float(cfg["x"]); zy = float(cfg["y"])
                zw = float(cfg["w"]); zh = float(cfg["h"])
            except (KeyError, TypeError, ValueError):
                continue
            if max(zx, zy, zw, zh) <= 1.0:
                zx *= native_w; zy *= native_h
                zw *= native_w; zh *= native_h
            draw.rectangle([zx, zy, zx + zw, zy + zh],
                            outline=(0, 180, 255, 255), width=2,
                            fill=(0, 180, 255, 40))
            draw.text((zx + 2, max(0, zy - 16)), f["name"],
                       fill=(0, 120, 200, 255), font=font)
    bg_img = overlay

with st.container(height=720, border=True):
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.2)",
        stroke_width=2,
        stroke_color="#FF0000",
        background_image=bg_img,
        update_streamlit=True,
        height=disp_h,
        width=disp_w,
        drawing_mode="rect",
        key=f"canvas_{tid}_{page['page_index']}",
    )
components.html(
    """
    <script>
    (function setup() {
        const pdoc = window.parent.document;
        const iframes = pdoc.querySelectorAll('iframe[title*="drawable_canvas" i]');
        const iframe = iframes[iframes.length - 1];
        if (!iframe) { setTimeout(setup, 250); return; }
        const wrapper = iframe.closest('div[data-testid="stVerticalBlockBorderWrapper"]');
        if (!wrapper) { setTimeout(setup, 250); return; }
        const idoc = iframe.contentDocument;
        if (!idoc || !idoc.body) { setTimeout(setup, 250); return; }
        if (idoc.__csaiPan) return;
        idoc.__csaiPan = true;
        let panning = false, sx = 0, sy = 0, lx = 0, ly = 0;
        idoc.addEventListener('mousedown', (e) => {
            if (e.button !== 1) return;
            e.preventDefault();
            panning = true;
            sx = e.clientX; sy = e.clientY;
            lx = wrapper.scrollLeft; ly = wrapper.scrollTop;
            idoc.body.style.cursor = 'grabbing';
        }, true);
        idoc.addEventListener('mousemove', (e) => {
            if (!panning) return;
            wrapper.scrollLeft = lx - (e.clientX - sx);
            wrapper.scrollTop = ly - (e.clientY - sy);
        }, true);
        const stop = () => {
            if (!panning) return;
            panning = false;
            idoc.body.style.cursor = '';
        };
        idoc.addEventListener('mouseup', stop, true);
        idoc.addEventListener('mouseleave', stop, true);
        idoc.addEventListener('auxclick', (e) => {
            if (e.button === 1) e.preventDefault();
        }, true);
    })();
    </script>
    """,
    height=0,
)

st.divider()
st.subheader("Convert last rect → field")
with st.container():
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

        preview_lines = st.session_state.get(lines_key)
        preview_min_overlap = st.slider(
            "min_overlap (preview + saved)", 0.0, 1.0, 0.3, 0.05,
            key=f"minov_{tid}_{page['page_index']}_{len(rects)}",
        )
        if preview_lines is None:
            st.info("Load OCR lines above to see live preview.")
            preview_text = None
        else:
            zone = (x, y, x + w, y + h)
            hits = []
            for ln in preview_lines:
                if "bbox" not in ln:
                    continue
                r_ov = _overlap_ratio(ln["bbox"], zone)
                if r_ov >= preview_min_overlap:
                    hits.append((ln, r_ov))
            hits.sort(key=lambda t: (t[0]["bbox"][1], t[0]["bbox"][0]))
            if not hits:
                st.warning("No lines match this zone. Draw bigger box "
                           "or lower min_overlap.")
                preview_text = None
            else:
                st.markdown("**Preview (captured lines)**")
                for ln, r_ov in hits:
                    st.caption(f"• [{r_ov:.0%}] {ln['text']}")
                preview_text = " ".join(ln["text"] for ln, _ in hits)
                st.success(f"Merged: `{preview_text}`")

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
                        "config": {"x": x, "y": y, "w": w, "h": h,
                                    "merge": merge,
                                    "min_overlap": float(preview_min_overlap)},
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
raw_key = f"raw_{tid}"
hash_key = f"raw_hash_{tid}"
current_hash = hash(json.dumps(draft, sort_keys=True))
if st.session_state.get(hash_key) != current_hash:
    st.session_state[raw_key] = json.dumps(draft, indent=2)
    st.session_state[hash_key] = current_hash
edited_raw = st.text_area("Edit raw JSON (optional)",
                           height=260, key=raw_key)
c_apply, c_save = st.columns(2)
if c_apply.button("Apply JSON to draft"):
    try:
        parsed = json.loads(edited_raw)
        st.session_state[draft_key] = parsed
        st.session_state[hash_key] = hash(json.dumps(parsed, sort_keys=True))
        st.success("Draft updated.")
        st.rerun()
    except Exception as e:
        st.error(f"Invalid JSON: {e}")
save_mode = st.radio(
    "Save mode", ["In-place (overwrite)", "New version"],
    horizontal=True, index=0, key=f"savemode_{tid}",
)
if c_save.button("Save", type="primary"):
    in_place = save_mode.startswith("In-place")
    try:
        new = update_template(tid, None, st.session_state[draft_key],
                               in_place=in_place)
        if in_place:
            st.success(f"Saved in place · template #{new['id']} v{new['version']}")
        else:
            st.success(f"Saved as new version · template #{new['id']} v{new['version']}")
        st.session_state["selected_template_id"] = new["id"]
        st.session_state.pop(draft_key, None)
        st.rerun()
    except Exception as e:
        st.error(_err(e))
