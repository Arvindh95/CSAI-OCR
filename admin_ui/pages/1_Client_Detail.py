import httpx
import streamlit as st

from admin_ui._url_fix import fix_url
from admin_ui.api import get_client, get_plan, get_usage, list_jobs

st.set_page_config(page_title="Client Detail", layout="wide")
fix_url()

cid = st.session_state.get("selected_client_id")
if not cid:
    cid = st.number_input("Client ID", min_value=1, step=1, value=1)
    if not st.button("Load"):
        st.stop()
    st.session_state["selected_client_id"] = int(cid)
    cid = int(cid)

try:
    client = get_client(cid)
    plan = get_plan(cid)
    usage = get_usage(cid)
except httpx.HTTPStatusError as e:
    st.error(f"API {e.response.status_code}: {e.response.text}")
    st.stop()
except httpx.HTTPError as e:
    st.error(f"API error: {e}")
    st.stop()

status_badge = "✅ active" if client["is_active"] else "⛔ inactive"
st.title(f"Client #{client['id']} — {client['name']}")
st.caption(f"{client['email']} · {status_badge}")

c1, c2, c3 = st.columns(3)
c1.metric("Used this period", usage["used"])
c2.metric("Limit", usage["limit"])
c3.metric("Remaining", usage["remaining"])
st.caption(f"Period {usage['period_start'][:10]} → {usage['period_end'][:10]}")

with st.expander("Plan", expanded=True):
    st.json({
        "max_transactions": plan["max_transactions"],
        "max_pages_per_txn": plan["max_pages_per_txn"],
        "reset_period": plan["reset_period"],
        "effective_from": plan["effective_from"],
    })

st.subheader("Jobs")
f1, f2 = st.columns([1, 4])
with f1:
    status_filter = st.selectbox("Status", ["all", "queued", "running", "done", "failed"], index=0)
    filter_val = None if status_filter == "all" else status_filter
try:
    jobs = list_jobs(cid, status=filter_val, limit=100)
except httpx.HTTPError as e:
    st.error(f"Jobs fetch failed: {e}")
    jobs = []

if not jobs:
    st.info("No jobs for this client yet.")
else:
    rows = [
        {
            "Job ID": j["job_id"][:8] + "…",
            "Endpoint": j["endpoint"],
            "Status": j["status"],
            "Pages": j["pages_submitted"],
            "Queued": (j["queued_at"] or "")[:19].replace("T", " "),
            "Completed": (j["completed_at"] or "—")[:19].replace("T", " "),
            "Error": (j["error_msg"] or "")[:60],
        }
        for j in jobs
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

st.caption("Actions (rotate key, reset quota, edit plan, deactivate) → **Actions** page.")
