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

_flash = st.session_state.pop("tpl_flash", None)
if _flash:
    _kind, _msg = _flash
    {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}.get(_kind, st.info)(_msg)


def _flash_and_rerun(kind: str, msg: str) -> None:
    st.session_state["tpl_flash"] = (kind, msg)
    st.rerun()

FORM_STRATEGIES = ["anchor", "regex", "between"]
ANCHOR_DIRS = ["same_line_colon", "right", "below"]
POST_PROCESS_OPTS = ["", "trim", "uppercase", "lowercase", "number", "date"]
FORM_KEYS = [
    "ff_name", "ff_pi", "ff_strat", "ff_pp", "ff_req", "ff_do",
    "ff_labels", "ff_dir", "ff_md",
    "ff_pat", "ff_grp", "ff_ic",
    "ff_aft", "ff_bef", "ff_bic", "ff_skip", "ff_col",
]


def _reset_form_state() -> None:
    for k in FORM_KEYS:
        st.session_state.pop(k, None)


def _seed_form_state(field: dict) -> None:
    _reset_form_state()
    cfg = field.get("config") or {}
    st.session_state["ff_name"] = field.get("name", "")
    st.session_state["ff_pi"] = int(field.get("page_index", 0))
    st.session_state["ff_strat"] = field.get("strategy", "anchor")
    st.session_state["ff_pp"] = field.get("post_process") or ""
    st.session_state["ff_req"] = bool(field.get("required", True))
    st.session_state["ff_do"] = int(field.get("display_order", 0))
    if field.get("strategy") == "anchor":
        st.session_state["ff_labels"] = "\n".join(cfg.get("labels", []))
        st.session_state["ff_dir"] = cfg.get("direction", "same_line_colon")
        st.session_state["ff_md"] = int(cfg.get("max_distance_px", 0) or 0)
    elif field.get("strategy") == "regex":
        st.session_state["ff_pat"] = cfg.get("pattern", "")
        st.session_state["ff_grp"] = int(cfg.get("group", 0))
        st.session_state["ff_ic"] = bool(cfg.get("ignore_case", True))
    elif field.get("strategy") == "between":
        st.session_state["ff_aft"] = cfg.get("after", "")
        st.session_state["ff_bef"] = cfg.get("before", "") or ""
        st.session_state["ff_bic"] = bool(cfg.get("ignore_case", True))
        st.session_state["ff_skip"] = "\n".join(cfg.get("skip_after", []))
        st.session_state["ff_col"] = bool(cfg.get("collapse_whitespace", True))


def _build_field_from_form(strategy: str, draft_len: int) -> tuple[dict | None, str | None]:
    name = (st.session_state.get("ff_name") or "").strip()
    if not name:
        return None, "Field name required."
    if strategy == "anchor":
        labels = [
            ln.strip() for ln in (st.session_state.get("ff_labels") or "").splitlines()
            if ln.strip()
        ]
        if not labels:
            return None, "Anchor needs at least one label."
        config: dict = {"labels": labels, "direction": st.session_state.get("ff_dir", "same_line_colon")}
        md = int(st.session_state.get("ff_md", 0) or 0)
        if md > 0:
            config["max_distance_px"] = md
    elif strategy == "regex":
        pattern = st.session_state.get("ff_pat") or ""
        if not pattern:
            return None, "Regex pattern required."
        config = {
            "pattern": pattern,
            "group": int(st.session_state.get("ff_grp", 0) or 0),
            "ignore_case": bool(st.session_state.get("ff_ic", True)),
        }
    elif strategy == "between":
        after = (st.session_state.get("ff_aft") or "").strip()
        if not after:
            return None, "`after` phrase required."
        config = {
            "after": after,
            "ignore_case": bool(st.session_state.get("ff_bic", True)),
            "collapse_whitespace": bool(st.session_state.get("ff_col", True)),
        }
        before = (st.session_state.get("ff_bef") or "").strip()
        if before:
            config["before"] = before
        skip = [
            ln.strip() for ln in (st.session_state.get("ff_skip") or "").splitlines()
            if ln.strip()
        ]
        if skip:
            config["skip_after"] = skip
    else:
        return None, f"Unsupported strategy in form: {strategy}"

    return {
        "name": name,
        "page_index": int(st.session_state.get("ff_pi", 0) or 0),
        "strategy": strategy,
        "config": config,
        "post_process": (st.session_state.get("ff_pp") or "") or None,
        "required": bool(st.session_state.get("ff_req", True)),
        "display_order": int(st.session_state.get("ff_do", draft_len) or 0),
    }, None


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

# ── Sample pages ──────────────────────────────────────────────────────────────
sp_col, _ = st.columns([1, 1])
with sp_col:
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
                    _flash_and_rerun("success", "Uploaded.")
                except Exception as e:
                    st.error(err_to_str(e))

st.divider()

# ── Fields editor (form + list/JSON) ──────────────────────────────────────────
st.subheader("Fields")

draft_key = f"draft_fields_{tpl['id']}"
if (draft_key not in st.session_state
        or st.session_state.get("draft_for_tpl") != tpl["id"]):
    st.session_state[draft_key] = [
        {"name": f["name"], "page_index": f["page_index"],
         "strategy": f["strategy"], "config": f["config"],
         "post_process": f["post_process"], "required": f["required"],
         "display_order": f["display_order"]}
        for f in tpl["fields"]
    ]
    st.session_state["draft_for_tpl"] = tpl["id"]
    st.session_state["edit_idx"] = None
    _reset_form_state()

draft: list[dict] = st.session_state[draft_key]
edit_idx = st.session_state.get("edit_idx")
editing = edit_idx is not None and 0 <= edit_idx < len(draft)

# seed widget defaults via session_state (avoids "default + key" warnings)
st.session_state.setdefault("ff_name", "")
st.session_state.setdefault("ff_pi", 0)
st.session_state.setdefault("ff_strat", "anchor")
st.session_state.setdefault("ff_pp", "")
st.session_state.setdefault("ff_req", True)
st.session_state.setdefault("ff_do", len(draft))
st.session_state.setdefault("ff_labels", "")
st.session_state.setdefault("ff_dir", "same_line_colon")
st.session_state.setdefault("ff_md", 0)
st.session_state.setdefault("ff_pat", "")
st.session_state.setdefault("ff_grp", 0)
st.session_state.setdefault("ff_ic", True)
st.session_state.setdefault("ff_aft", "")
st.session_state.setdefault("ff_bef", "")
st.session_state.setdefault("ff_bic", True)
st.session_state.setdefault("ff_skip", "")
st.session_state.setdefault("ff_col", True)

ff_col, fl_col = st.columns(2)

# ── Form column ───────────────────────────────────────────────────────────────
with ff_col:
    st.markdown(f"**{'Edit field #' + str(edit_idx) if editing else 'Add new field'}**")
    if editing and draft[edit_idx]["strategy"] == "zone":
        st.warning("This is a `zone` field. Edit on the Annotate page (canvas-based). "
                   "You can change post_process / required / display_order here, "
                   "but the strategy switch will discard the zone bbox.")

    st.text_input("Field name", key="ff_name",
                  placeholder="e.g. nama_perniagaan")
    st.number_input("Page index", min_value=0, step=1, key="ff_pi")

    if st.session_state.get("ff_strat") not in FORM_STRATEGIES:
        st.session_state["ff_strat"] = "anchor"
    strategy = st.selectbox("Strategy", FORM_STRATEGIES, key="ff_strat")

    if strategy == "anchor":
        st.text_area("Labels (one per line)", key="ff_labels",
                     placeholder="NAMA PERNIAGAAN\nBUSINESS NAME",
                     height=90)
        st.selectbox("Direction", ANCHOR_DIRS, key="ff_dir",
                     help="same_line_colon = grab text after `:` on same line; "
                          "right = nearest box to the right; "
                          "below = nearest box below")
        st.number_input("max_distance_px (0 = unlimited)", min_value=0,
                        step=10, key="ff_md")
    elif strategy == "regex":
        st.text_input("Pattern (Python regex)", key="ff_pat",
                      placeholder=r"(MA\d{7}-[A-Z])")
        st.number_input("Capture group", min_value=0, step=1, key="ff_grp",
                        help="0 = full match, 1 = first capture group")
        st.checkbox("ignore_case", key="ff_ic")
    elif strategy == "between":
        st.text_input("after (phrase before value)", key="ff_aft",
                      placeholder="tempat utama perniagaannya")
        st.text_input("before (phrase after value, optional)", key="ff_bef",
                      placeholder="Jenis Perniagaan")
        st.checkbox("ignore_case", key="ff_bic")
        st.text_area("skip_after tokens (one per line, optional)",
                     key="ff_skip", placeholder="di",
                     help="Drop these leading tokens from the captured value.",
                     height=70)
        st.checkbox("collapse_whitespace", key="ff_col",
                    help="Replace OCR line-breaks with single space.")

    if st.session_state.get("ff_pp") not in POST_PROCESS_OPTS:
        st.session_state["ff_pp"] = ""
    st.selectbox("post_process", POST_PROCESS_OPTS, key="ff_pp")
    st.checkbox("required", key="ff_req")
    st.number_input("display_order", min_value=0, step=1, key="ff_do")

    btn_label = "Update field" if editing else "Add field"
    bcol1, bcol2 = st.columns(2)
    if bcol1.button(btn_label, type="primary", key="ff_submit"):
        new_field, err = _build_field_from_form(strategy, len(draft))
        if err:
            st.error(err)
        else:
            if editing:
                draft[edit_idx] = new_field
                st.session_state["edit_idx"] = None
            else:
                draft.append(new_field)
            _reset_form_state()
            st.rerun()
    if editing and bcol2.button("Cancel edit", key="ff_cancel"):
        st.session_state["edit_idx"] = None
        _reset_form_state()
        st.rerun()
    if not editing and bcol2.button("Reset form", key="ff_reset"):
        _reset_form_state()
        st.rerun()

# ── List + JSON column ────────────────────────────────────────────────────────
with fl_col:
    st.markdown(f"**Draft fields ({len(draft)})**")
    if not draft:
        st.caption("_No fields yet — add one with the form on the left._")
    else:
        sorted_idx = sorted(range(len(draft)),
                            key=lambda i: (draft[i]["display_order"], i))
        for idx in sorted_idx:
            f = draft[idx]
            r1, r2, r3 = st.columns([6, 1, 1])
            with r1:
                req_mark = "★" if f.get("required") else " "
                pp = f.get("post_process") or "—"
                st.markdown(
                    f"`#{f['display_order']}` {req_mark} "
                    f"**{f['name']}** · `{f['strategy']}` · pg{f['page_index']} · pp:`{pp}`"
                )
            if r2.button("✏", key=f"edit-{idx}",
                         disabled=f["strategy"] not in FORM_STRATEGIES,
                         help=("Edit on Annotate page" if f["strategy"] == "zone"
                               else "Load into form")):
                _seed_form_state(f)
                st.session_state["edit_idx"] = idx
                st.rerun()
            if r3.button("✕", key=f"del-{idx}", help="Remove from draft"):
                draft.pop(idx)
                if st.session_state.get("edit_idx") == idx:
                    st.session_state["edit_idx"] = None
                    _reset_form_state()
                elif (st.session_state.get("edit_idx") or 0) > idx:
                    st.session_state["edit_idx"] -= 1
                st.rerun()

    st.divider()
    edited = st.text_area("fields JSON (raw)",
                           value=json.dumps(draft, indent=2),
                           height=260, key=f"ed-{tpl['id']}")
    if st.button("Apply JSON to draft", key=f"apply-{tpl['id']}"):
        try:
            parsed = json.loads(edited) if edited.strip() else []
            if not isinstance(parsed, list):
                raise ValueError("must be a JSON array")
        except Exception as e:
            st.error(f"Invalid JSON: {e}")
        else:
            st.session_state[draft_key] = parsed
            st.session_state["edit_idx"] = None
            _reset_form_state()
            st.rerun()

# ── Save / delete (full-width below) ──────────────────────────────────────────
st.divider()
e_name = st.text_input("New name (blank = keep)", value=tpl["name"],
                         key=f"nm-{tpl['id']}")
save_mode = st.radio(
    "Save mode", ["In-place (overwrite)", "New version"],
    horizontal=True, index=0, key=f"sm-{tpl['id']}",
)
c_save, c_del = st.columns(2)
if c_save.button("Save", type="primary", key=f"sv-{tpl['id']}"):
    in_place = save_mode.startswith("In-place")
    try:
        new = update_template(tpl["id"], e_name or None, draft,
                               in_place=in_place)
        label = "in place" if in_place else "new version"
        st.session_state["selected_template_id"] = new["id"]
        for k in list(st.session_state.keys()):
            if k.startswith("draft_fields_") or k == "draft_for_tpl":
                del st.session_state[k]
        st.session_state["edit_idx"] = None
        _reset_form_state()
        _flash_and_rerun(
            "success",
            f"Saved {label} · template #{new['id']} v{new['version']}",
        )
    except Exception as e:
        st.error(err_to_str(e))

del_mode = c_del.radio(
    "Delete mode", ["Soft (deactivate)", "Hard (permanent)"],
    horizontal=False, key=f"dm-{tpl['id']}",
)
confirm = c_del.checkbox("Confirm delete", key=f"cd-{tpl['id']}")
if c_del.button("Delete", disabled=not confirm, key=f"db-{tpl['id']}"):
    hard = del_mode.startswith("Hard")
    try:
        delete_template(tpl["id"], hard=hard)
        st.session_state.pop("selected_template_id", None)
        _flash_and_rerun(
            "success",
            "Permanently deleted." if hard else "Soft-deleted.",
        )
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
