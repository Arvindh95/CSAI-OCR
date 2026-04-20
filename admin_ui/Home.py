import httpx
import streamlit as st

from admin_ui.api import list_clients

st.set_page_config(page_title="CSAI-OCR Admin", page_icon="🔐", layout="wide")
st.title("CSAI-OCR Admin")
st.caption("Client management dashboard")

col1, col2 = st.columns([1, 4])
with col1:
    active_only = st.checkbox("Active only", value=False)
with col2:
    if st.button("🔄 Refresh", use_container_width=False):
        st.rerun()

try:
    clients = list_clients(active_only=active_only)
except httpx.HTTPError as e:
    st.error(f"API error: {e}")
    st.stop()

if not clients:
    st.info("No clients found. Create one on the **Actions** page.")
    st.stop()

st.metric("Total clients", len(clients))

rows = [
    {
        "ID": c["id"],
        "Name": c["name"],
        "Email": c["email"],
        "Prefix": c["api_key_prefix"],
        "Active": "✅" if c["is_active"] else "⛔",
        "Created": c["created_at"][:19].replace("T", " "),
    }
    for c in clients
]

st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Open a client")
cid = st.number_input("Client ID", min_value=1, step=1, value=clients[0]["id"])
if st.button("Open", type="primary"):
    st.session_state["selected_client_id"] = int(cid)
    st.switch_page("pages/1_Client_Detail.py")
