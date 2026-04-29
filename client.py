"""
SSM Verifier — Local Client
Run: streamlit run client.py
"""

import requests
import streamlit as st

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="SSM Verifier",
    page_icon="📄",
    layout="wide"
)

st.title("📄 SSM Document Verifier")

# ── Sidebar — endpoint config ─────────────────────────────────
with st.sidebar:
    st.header("Server Settings")

    base_url = st.text_input(
        "API Base URL",
        value=st.session_state.get("base_url", "https://your-server.example.com"),
        placeholder="http://your-server:8000"
    )
    st.session_state["base_url"] = base_url.rstrip("/")

    st.divider()
    st.subheader("Endpoints")
    st.caption(f"Health: `{base_url}/health`")
    st.caption(f"OCR:    `{base_url}/ocr`")
    st.caption(f"Verify: `{base_url}/verify`")

    st.divider()
    st.subheader("Health Check")
    if st.button("Check Server", use_container_width=True):
        try:
            r = requests.get(f"{st.session_state['base_url']}/health", timeout=5)
            data = r.json()
            if r.status_code == 200 and data.get("status") == "ok":
                st.success("Server Online")
                st.json(data)
            else:
                st.error("Server returned error")
                st.json(data)
        except requests.exceptions.ConnectionError:
            st.error("Cannot connect to server")
        except requests.exceptions.Timeout:
            st.error("Connection timed out")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Main — two columns ────────────────────────────────────────
col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.subheader("1. Upload SSM Document")
    uploaded = st.file_uploader(
        "Upload image",
        type=["jpg", "jpeg", "png", "bmp", "tiff"],
        label_visibility="collapsed"
    )
    if uploaded:
        st.image(uploaded, caption=uploaded.name, use_container_width=True)

with col_right:
    st.subheader("2. Enter Details")
    input_name = st.text_input(
        "Business Name",
        placeholder="e.g. DFG TELECOMMUNICATION"
    )
    input_reg = st.text_input(
        "Registration Number",
        placeholder="e.g. MA0127232-D"
    )
    st.write("")
    verify_btn = st.button("Verify Document", type="primary", use_container_width=True)
    extract_btn = st.button("Extract Fields Only", use_container_width=True)

# ── Actions ───────────────────────────────────────────────────
def call_api(endpoint, file, extra_data=None):
    url = f"{st.session_state['base_url']}/{endpoint}"
    files = {"file": (file.name, file.getvalue(), "image/jpeg")}
    try:
        r = requests.post(url, files=files, data=extra_data or {}, timeout=120)
        if r.status_code == 200:
            return r.json(), None
        else:
            return None, f"Server error {r.status_code}: {r.text[:200]}"
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to server. Check URL in sidebar."
    except requests.exceptions.Timeout:
        return None, "Request timed out (>120s)."
    except Exception as e:
        return None, str(e)


def show_fields(fields):
    if not fields:
        st.warning("No fields extracted.")
        return
    # exclude internal keys
    items = [(k, v) for k, v in fields.items() if not k.startswith("_")]
    cols = st.columns(2)
    half = (len(items) + 1) // 2
    with cols[0]:
        for k, v in items[:half]:
            st.markdown(f"**{k.replace('_', ' ').title()}**")
            st.code(v, language=None)
    with cols[1]:
        for k, v in items[half:]:
            st.markdown(f"**{k.replace('_', ' ').title()}**")
            st.code(v, language=None)


def show_expiry(fields):
    expiry = fields.get("_expiry_check", {})
    if not expiry or expiry.get("expired") is None:
        return
    st.divider()
    st.subheader("Expiry Status")
    if expiry.get("expired"):
        st.error(f"EXPIRED — {expiry.get('note', '')}")
    else:
        st.success(f"VALID — {expiry.get('note', '')}")


def show_verification(verification, verified):
    st.divider()
    st.subheader("Verification Result")

    if verified:
        st.success("VERIFIED — All fields match.")
    else:
        st.error("NOT VERIFIED — One or more fields do not match.")

    for field, res in verification.items():
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{field.replace('_', ' ').title()}**")
                st.markdown(f"Input &nbsp;&nbsp;: `{res['input']}`")
                st.markdown(f"Found &nbsp;: `{res['extracted']}`")
            with c2:
                st.write("")
                st.write("")
                if res["match"]:
                    st.success("MATCH")
                else:
                    st.error("MISMATCH")


# ── Verify ────────────────────────────────────────────────────
if verify_btn:
    if not uploaded:
        st.error("Upload a document first.")
    elif not input_name.strip() and not input_reg.strip():
        st.warning("Enter at least Business Name or Registration Number.")
    else:
        with st.spinner("Sending to OCR server..."):
            data, err = call_api(
                "verify", uploaded,
                extra_data={"name": input_name, "reg_no": input_reg}
            )
        if err:
            st.error(err)
        else:
            st.divider()
            st.subheader("Extracted Fields")
            show_fields(data.get("fields", {}))
            show_expiry(data.get("fields", {}))
            show_verification(data.get("verification", {}), data.get("verified", False))

# ── Extract only ──────────────────────────────────────────────
if extract_btn:
    if not uploaded:
        st.error("Upload a document first.")
    else:
        with st.spinner("Extracting fields..."):
            data, err = call_api("ocr", uploaded)
        if err:
            st.error(err)
        else:
            st.divider()
            st.subheader("Extracted Fields")
            show_fields(data.get("fields", {}))
            show_expiry(data.get("fields", {}))

            with st.expander("Raw OCR lines"):
                for line in data.get("lines", []):
                    st.write(f"`[{line['confidence']:.2f}]` {line['text']}")
