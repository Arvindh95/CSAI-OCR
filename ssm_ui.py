"""
SSM Document Verifier — Streamlit UI
Run: streamlit run ssm_ui.py
"""

import os
import sys
import re
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image

# Cache dirs — all on D:
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", r"D:\docling\models\paddlex")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ["FLAGS_use_mkldnn"] = "0"

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="SSM Document Verifier",
    page_icon="📄",
    layout="wide"
)

st.title("📄 SSM Document Verifier")
st.caption("Upload an SSM document, enter details to verify — OCR checks for you.")

# ── Load OCR model once (cached) ──────────────────────────────
@st.cache_resource(show_spinner="Loading OCR model...")
def load_ocr():
    from paddleocr import PaddleOCR
    return PaddleOCR(lang="en", enable_mkldnn=False)


# ── OCR + Parse helpers ───────────────────────────────────────
def run_ocr(ocr, image_path):
    result = ocr.predict(str(image_path))
    lines = []
    for page in result:
        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        for text, score in zip(texts, scores):
            if text.strip():
                lines.append({"text": text.strip(), "conf": round(score, 3)})
    return lines


def clean(text):
    return re.sub(r"^[\s:]+", "", text).strip()


def parse_ssm(lines):
    texts = [l["text"] for l in lines]
    fields = {}

    for i, text in enumerate(texts):
        t = text.upper()

        # SSM format 1: label "NAMA PERNIAGAAN"
        if "NAMA PERNIAGAAN" in t and "NO" not in t and "ALAMAT" not in t:
            if i + 1 < len(texts):
                fields["Company Name"] = clean(texts[i + 1])

        # SSM format 2 (Borang D): after "dijalankan dengan nama"
        if "DIJALANKAN DENGAN NAMA" in t or "dijalankan dengan nama" in text:
            if i + 1 < len(texts):
                fields["Company Name"] = clean(texts[i + 1])

        if "NO PENDAFTARAN PERNIAGAAN" in t or "NO. PENDAFTARAN" in t:
            if i + 1 < len(texts):
                fields["Registration No"] = clean(texts[i + 1])
            colon_val = re.search(r":(.+)", text)
            if colon_val and len(colon_val.group(1).strip()) > 2:
                fields["Registration No"] = colon_val.group(1).strip()

        if "ALAMAT UTAMA PERNIAGAAN" in t:
            addr_parts = []
            for j in range(i + 1, min(i + 5, len(texts))):
                val = clean(texts[j])
                if any(kw in texts[j].upper() for kw in ["BENTUK", "TARIKH", "STATUS", "JENIS"]):
                    break
                if val:
                    addr_parts.append(val)
            fields["Address"] = ", ".join(addr_parts)

        if "BENTUK PERNIAGAAN" in t:
            if i + 1 < len(texts):
                fields["Business Type"] = clean(texts[i + 1])

        if t.strip() == "STATUS" or (t.startswith("STATUS") and len(t) < 20):
            if i + 1 < len(texts):
                fields["Status"] = clean(texts[i + 1])

        if "TARIKH LUPUT" in t:
            if i + 1 < len(texts):
                fields["Expiry Date"] = clean(texts[i + 1])

        if "TARIKH PENDAFTARAN" in t and "LUPUT" not in t:
            if i + 1 < len(texts):
                fields["Registration Date"] = clean(texts[i + 1])

    return fields


def verify(fields, check_name, check_reg):
    results = {}

    if check_name.strip():
        extracted = fields.get("Company Name", "")
        match = check_name.strip().upper() == extracted.strip().upper()
        results["Company Name"] = {
            "input": check_name.strip(),
            "extracted": extracted,
            "match": match
        }

    if check_reg.strip():
        extracted = fields.get("Registration No", "")
        # strip spaces only — preserve dashes, case insensitive
        match = check_reg.strip().upper() == extracted.strip().upper()
        results["Registration No"] = {
            "input": check_reg.strip(),
            "extracted": extracted,
            "match": match
        }

    return results


# ── Layout ────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.subheader("1. Upload Document")
    uploaded = st.file_uploader(
        "Upload SSM document image",
        type=["jpg", "jpeg", "png", "bmp", "tiff"],
        label_visibility="collapsed"
    )
    if uploaded:
        img = Image.open(uploaded)
        st.image(img, caption=uploaded.name, use_container_width=True)

with col_right:
    st.subheader("2. Enter Details to Verify")
    input_name = st.text_input(
        "Company Name",
        placeholder="e.g. DFG TELECOMMUNICATION"
    )
    input_reg = st.text_input(
        "Registration Number",
        placeholder="e.g. MA0127232-D"
    )

    st.write("")
    run_btn = st.button("Verify Document", type="primary", use_container_width=True)

# ── Run on button click ───────────────────────────────────────
if run_btn:
    if not uploaded:
        st.error("Please upload a document image first.")
    elif not input_name.strip() and not input_reg.strip():
        st.warning("Enter at least one field to verify.")
    else:
        with st.spinner("Running OCR... this may take ~30-60s on CPU"):
            # Save upload to temp file
            suffix = Path(uploaded.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = tmp.name

            ocr = load_ocr()
            lines = run_ocr(ocr, tmp_path)
            fields = parse_ssm(lines)
            verification = verify(fields, input_name, input_reg)


            os.unlink(tmp_path)

        st.divider()

        # ── Extracted fields ──────────────────────────────────
        st.subheader("Extracted Fields")
        if fields:
            field_col1, field_col2 = st.columns(2)
            items = list(fields.items())
            half = (len(items) + 1) // 2
            with field_col1:
                for k, v in items[:half]:
                    st.markdown(f"**{k}**")
                    st.code(v, language=None)
            with field_col2:
                for k, v in items[half:]:
                    st.markdown(f"**{k}**")
                    st.code(v, language=None)
        else:
            st.warning("No fields extracted. Check image quality.")

        # ── Verification results ──────────────────────────────
        if verification:
            st.divider()
            st.subheader("Verification Results")

            all_match = all(r["match"] for r in verification.values())

            if all_match:
                st.success("All fields MATCH — document verified.")
            else:
                st.error("One or more fields do NOT match.")

            for field, res in verification.items():
                with st.container(border=True):
                    v_col1, v_col2 = st.columns([4, 1])
                    with v_col1:
                        st.markdown(f"**{field}**")
                        st.markdown(f"Input &nbsp;&nbsp;: `{res['input']}`")
                        st.markdown(f"Found &nbsp;: `{res['extracted']}`")
                    with v_col2:
                        st.write("")
                        st.write("")
                        if res["match"]:
                            st.success("MATCH")
                        else:
                            st.error("MISMATCH")

        # ── Raw OCR output (expandable) ───────────────────────
        with st.expander("View raw OCR output"):
            for l in lines:
                st.write(f"`[{l['conf']:.2f}]` {l['text']}")
