import httpx
import streamlit as st

from admin_ui._url_fix import fix_url
from admin_ui.api import (
    create_client,
    deactivate_client,
    get_client,
    get_plan,
    reset_quota,
    rotate_key,
    update_client,
    upsert_plan,
)

st.set_page_config(page_title="Actions", layout="wide")
fix_url()
st.title("Actions")


def _err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"API {e.response.status_code}: {e.response.text}"
    return f"API error: {e}"


st.header("Create client")
with st.form("create"):
    c1, c2 = st.columns(2)
    name = c1.text_input("Name")
    email = c2.text_input("Email")
    c3, c4, c5 = st.columns(3)
    max_tx = c3.number_input("Max transactions", min_value=1, value=100, step=1)
    max_pages = c4.number_input("Max pages / txn", min_value=1, value=1, step=1)
    reset_period = c5.selectbox("Reset period", ["monthly", "lifetime"], index=0)
    submitted = st.form_submit_button("Create", type="primary")
    if submitted:
        if not name or not email:
            st.error("Name and email required.")
        else:
            try:
                created = create_client(name, email, int(max_tx), int(max_pages), reset_period)
                st.success(f"Created client #{created['id']}")
                st.warning("Copy the API key now — shown once.")
                st.code(created["api_key"], language=None)
                st.session_state["selected_client_id"] = created["id"]
            except Exception as e:
                st.error(_err(e))

st.divider()

st.header("Client operations")
stored = st.session_state.get("selected_client_id")
cid = st.number_input("Client ID", min_value=1, step=1,
                      value=int(stored) if stored else 1)
cid = int(cid)

try:
    client = get_client(cid)
    plan = get_plan(cid)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        st.info(f"No client #{cid}. Create one above or enter a valid ID.")
    else:
        st.error(_err(e))
    st.stop()
except Exception as e:
    st.error(_err(e))
    st.stop()

st.caption(f"#{client['id']} · {client['name']} · {client['email']} · "
           f"{'✅ active' if client['is_active'] else '⛔ inactive'}")

st.subheader("Rotate API key")
confirm_rot = st.checkbox(f"Confirm: invalidate current key for client #{cid}")
if st.button("Rotate key", disabled=not confirm_rot):
    try:
        rr = rotate_key(cid)
        st.success("Rotated. New key — shown once:")
        st.code(rr["api_key"], language=None)
    except Exception as e:
        st.error(_err(e))

st.divider()

st.subheader("Plan upsert")
with st.form("plan"):
    p1, p2, p3 = st.columns(3)
    new_max_tx = p1.number_input("Max transactions", min_value=1,
                                  value=int(plan["max_transactions"]), step=1)
    new_max_pages = p2.number_input("Max pages / txn", min_value=1,
                                     value=int(plan["max_pages_per_txn"]), step=1)
    new_reset = p3.selectbox("Reset period", ["monthly", "lifetime"],
                              index=0 if plan["reset_period"] == "monthly" else 1)
    if st.form_submit_button("Save plan", type="primary"):
        try:
            p = upsert_plan(cid, int(new_max_tx), int(new_max_pages), new_reset)
            st.success(f"Plan updated: {p['max_transactions']} tx, "
                       f"{p['max_pages_per_txn']} pp, {p['reset_period']}")
        except Exception as e:
            st.error(_err(e))

st.divider()

st.subheader("Reset quota")
confirm_q = st.checkbox(f"Confirm: reset used counter for client #{cid}")
if st.button("Reset quota", disabled=not confirm_q):
    try:
        u = reset_quota(cid)
        st.success(f"Quota reset. used={u['used']} limit={u['limit']}")
    except Exception as e:
        st.error(_err(e))

st.divider()

st.subheader("Edit name / email")
with st.form("edit"):
    e1, e2 = st.columns(2)
    new_name = e1.text_input("Name", value=client["name"])
    new_email = e2.text_input("Email", value=client["email"])
    if st.form_submit_button("Save"):
        try:
            patched = update_client(cid, name=new_name or None, email=new_email or None)
            st.success(f"Updated #{patched['id']}")
        except Exception as e:
            st.error(_err(e))

st.divider()

st.subheader("Deactivate / reactivate")
if client["is_active"]:
    confirm_d = st.checkbox(f"Confirm: deactivate client #{cid} (keys rejected 401)")
    if st.button("Deactivate", disabled=not confirm_d):
        try:
            d = deactivate_client(cid)
            st.success(f"Deactivated #{d['id']}. active={d['is_active']}")
        except Exception as e:
            st.error(_err(e))
else:
    if st.button("Reactivate"):
        try:
            r = update_client(cid, is_active=True)
            st.success(f"Reactivated #{r['id']}. active={r['is_active']}")
        except Exception as e:
            st.error(_err(e))
