import httpx
import streamlit as st

from admin_ui.api import (
    get_client,
    grant_template,
    list_client_templates,
    list_templates,
    revoke_template,
)

st.set_page_config(page_title="Client Templates", layout="wide")
st.title("Client template whitelist")


def _err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"API {e.response.status_code}: {e.response.text}"
    return f"API error: {e}"


stored = st.session_state.get("selected_client_id")
cid = st.number_input("Client ID", min_value=1, step=1,
                       value=int(stored) if stored else 1)
cid = int(cid)

try:
    client = get_client(cid)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        st.info(f"No client #{cid}. Enter a valid ID above.")
        st.stop()
    st.error(_err(e))
    st.stop()
except Exception as e:
    st.error(_err(e))
    st.stop()

st.caption(f"#{client['id']} · {client['name']} · {client['email']} · "
           f"{'✅ active' if client['is_active'] else '⛔ inactive'}")

try:
    granted = list_client_templates(cid)
    all_tpls = list_templates(active_only=True)
except Exception as e:
    st.error(_err(e))
    st.stop()

st.subheader("Currently granted")
if not granted:
    st.info("No templates granted to this client yet.")
else:
    for t in granted:
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.markdown(f"**{t['name']}** · `{t['doc_type_code']}` · v{t['version']}")
        c2.caption(f"id={t['id']}")
        if c3.button("Revoke", key=f"rv-{t['id']}"):
            try:
                revoke_template(cid, t["id"])
                st.success("Revoked.")
                st.rerun()
            except Exception as e:
                st.error(_err(e))

st.divider()
st.subheader("Grant a template")
granted_ids = {t["id"] for t in granted}
candidates = [t for t in all_tpls if t["id"] not in granted_ids
              and (t["client_id"] is None or t["client_id"] == cid)]
if not candidates:
    st.info("No eligible templates to grant.")
else:
    labels = {f"#{t['id']} · {t['name']} · {t['doc_type_code']} (v{t['version']})": t["id"]
              for t in candidates}
    pick = st.selectbox("Template", list(labels.keys()))
    if st.button("Grant", type="primary"):
        try:
            grant_template(cid, labels[pick])
            st.success("Granted.")
            st.rerun()
        except Exception as e:
            st.error(_err(e))
