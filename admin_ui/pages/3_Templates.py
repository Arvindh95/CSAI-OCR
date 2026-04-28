import json

import httpx
import streamlit as st

from admin_ui._errors import err_to_str

from admin_ui._url_fix import fix_url
from admin_ui.api import (
    create_template,
    delete_page,
    delete_template,
    get_template,
    list_templates,
    test_template,
    update_template,
    upload_page,
)

st.set_page_config(page_title="Templates", layout="wide")
fix_url()
st.title("Templates")

tab_list, tab_create = st.tabs(["Browse", "Create"])

with tab_list:
    c1, c2 = st.columns([1, 4])
    active_only = c1.checkbox("Active only", value=True)
    search = c2.text_input(
        "Search (ID, name, or doc_type_code)",
        placeholder="e.g. ssm, sijil, 54",
    )
    try:
        tmpls = list_templates(active_only=active_only,
                                q=search or None)
    except Exception as e:
        st.error(err_to_str(e))
        st.stop()
    if not tmpls:
        st.info("No templates. Create one on the Create tab.")
    else:
        rows = [
            {"ID": t["id"], "Name": t["name"], "Code": t["doc_type_code"],
             "Ver": t["version"],
             "Scope": "global" if t["client_id"] is None else f"client #{t['client_id']}",
             "Active": "✅" if t["is_active"] else "⛔",
             "Created": t["created_at"][:19].replace("T", " ")}
            for t in tmpls
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        options = {f"#{t['id']} — {t['name']}": t["id"] for t in tmpls}
        label = st.selectbox("Open template", list(options.keys()))
        if st.button("Open", type="primary"):
            st.session_state["selected_template_id"] = options[label]

with tab_create:
    with st.form("create_tpl"):
        name = st.text_input("Name")
        code = st.text_input("doc_type_code",
                              help="lowercase, digits, _ or -; unique while active")
        scope = st.radio("Scope", ["global", "client-specific"], horizontal=True)
        client_id = None
        if scope == "client-specific":
            client_id = st.number_input("Client ID", min_value=1, step=1, value=1)
        st.caption("Fields — JSON array; example below.")
        default = json.dumps([
            {"name": "invoice_no", "page_index": 0, "strategy": "anchor",
             "config": {"labels": ["INVOICE NO", "NO. INVOIS"],
                        "direction": "right", "max_distance_px": 300},
             "post_process": "trim", "required": True, "display_order": 1},
            {"name": "total", "page_index": 0, "strategy": "regex",
             "config": {"pattern": r"TOTAL[:\s]*RM?\s*([\d,\.]+)", "group": 1},
             "post_process": "number", "required": False, "display_order": 2},
        ], indent=2)
        fields_json = st.text_area("fields", value=default, height=280)
        if st.form_submit_button("Create", type="primary"):
            try:
                fields = json.loads(fields_json) if fields_json.strip() else []
            except Exception as e:
                st.error(f"Invalid JSON: {e}")
            else:
                try:
                    t = create_template(name.strip(), code.strip(),
                                         int(client_id) if client_id else None,
                                         fields)
                    st.success(f"Created template #{t['id']} v{t['version']}")
                    st.session_state["selected_template_id"] = t["id"]
                except Exception as e:
                    st.error(err_to_str(e))

sel = st.session_state.get("selected_template_id")
if not sel:
    st.stop()

st.divider()
st.header(f"Template #{sel}")
try:
    tpl = get_template(int(sel))
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        st.session_state.pop("selected_template_id", None)
        st.warning(f"Template #{sel} no longer exists. Pick another above.")
        st.stop()
    st.error(err_to_str(e))
    st.stop()
except Exception as e:
    st.error(err_to_str(e))
    st.stop()

scope = "global" if tpl["client_id"] is None else f"client #{tpl['client_id']}"
st.caption(f"**{tpl['name']}** · `{tpl['doc_type_code']}` · v{tpl['version']} · "
           f"{'✅ active' if tpl['is_active'] else '⛔ inactive'} · {scope}")

e1, e2 = st.columns(2)
with e1:
    st.subheader("Sample pages")
    if not tpl["pages"]:
        st.info("No pages uploaded.")
    else:
        for p in tpl["pages"]:
            st.markdown(f"- page **{p['page_index']}** · "
                        f"{p['image_width']}×{p['image_height']} · "
                        f"`{p['image_path']}`")
            if st.button(f"Delete page {p['page_index']}",
                         key=f"delpg-{p['page_index']}"):
                try:
                    delete_page(tpl["id"], p["page_index"])
                    st.rerun()
                except Exception as e:
                    st.error(err_to_str(e))
    with st.form(f"upl-{tpl['id']}"):
        page_idx = st.number_input("Page index (0-based)",
                                     min_value=0, step=1, value=0)
        up = st.file_uploader("Sample image", type=["png", "jpg", "jpeg"])
        if st.form_submit_button("Upload page"):
            if up is None:
                st.warning("Pick a file.")
            else:
                try:
                    upload_page(tpl["id"], int(page_idx),
                                 up.name, up.getvalue(), up.type or "image/png")
                    st.success("Uploaded.")
                    st.rerun()
                except Exception as e:
                    st.error(err_to_str(e))

with e2:
    st.subheader("Fields")
    fields_payload = [
        {"name": f["name"], "page_index": f["page_index"],
         "strategy": f["strategy"], "config": f["config"],
         "post_process": f["post_process"], "required": f["required"],
         "display_order": f["display_order"]}
        for f in tpl["fields"]
    ]
    edited = st.text_area("fields JSON",
                           value=json.dumps(fields_payload, indent=2),
                           height=350, key=f"ed-{tpl['id']}")
    e_name = st.text_input("New name (blank = keep)", value=tpl["name"],
                             key=f"nm-{tpl['id']}")
    save_mode = st.radio(
        "Save mode", ["In-place (overwrite)", "New version"],
        horizontal=True, index=0, key=f"sm-{tpl['id']}",
    )
    c_save, c_del = st.columns(2)
    if c_save.button("Save", type="primary"):
        try:
            parsed = json.loads(edited) if edited.strip() else []
        except Exception as e:
            st.error(f"Invalid JSON: {e}")
        else:
            in_place = save_mode.startswith("In-place")
            try:
                new = update_template(tpl["id"], e_name or None, parsed,
                                       in_place=in_place)
                label = "in place" if in_place else "new version"
                st.success(f"Saved {label} · template #{new['id']} v{new['version']}")
                st.session_state["selected_template_id"] = new["id"]
                st.rerun()
            except Exception as e:
                st.error(err_to_str(e))
    del_mode = c_del.radio(
        "Delete mode", ["Soft (deactivate)", "Hard (permanent)"],
        horizontal=False, key=f"dm-{tpl['id']}",
    )
    confirm = c_del.checkbox("Confirm delete", key=f"cd-{tpl['id']}")
    if c_del.button("Delete", disabled=not confirm):
        hard = del_mode.startswith("Hard")
        try:
            delete_template(tpl["id"], hard=hard)
            st.success("Permanently deleted." if hard else "Soft-deleted.")
            st.session_state.pop("selected_template_id", None)
            st.rerun()
        except Exception as e:
            st.error(err_to_str(e))

st.divider()
st.subheader("Test extraction")
tfile = st.file_uploader("Upload a test document (png/jpg/pdf)",
                          type=["png", "jpg", "jpeg", "pdf"],
                          key=f"tf-{tpl['id']}")
if st.button("Run test", disabled=tfile is None):
    if tfile is None:
        st.warning("Pick a file.")
    else:
        with st.spinner("Running OCR + extraction..."):
            try:
                res = test_template(tpl["id"], tfile.name, tfile.getvalue(),
                                     tfile.type or "application/octet-stream")
                st.success("Done.")
                st.markdown("**Extracted fields**")
                st.json(res["extracted"])
                with st.expander(f"Raw OCR lines ({len(res['lines'])})"):
                    st.json(res["lines"])
            except Exception as e:
                st.error(err_to_str(e))
