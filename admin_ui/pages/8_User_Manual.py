import streamlit as st

st.set_page_config(page_title="User Manual", layout="wide")
st.title("User Manual")

st.markdown("""
This manual covers the full admin workflow — from onboarding a client to annotating
templates and handing off API credentials.

---
""")

# ── Concepts ──────────────────────────────────────────────────────────────────
st.header("Key concepts")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown("**Client**")
    st.markdown("""
    An organisation or system that consumes the OCR API.
    Each client has an API key and belongs to a billing plan.
    """)

with c2:
    st.markdown("**Plan**")
    st.markdown("""
    Defines the transaction quota for a client (e.g. 1000 jobs/month).
    Quota resets on the billing period start date.
    """)

with c3:
    st.markdown("**Template**")
    st.markdown("""
    A document type definition (e.g. `sijil_ssm`). Contains one or more
    fields, each with an extraction strategy and optional post-processing.
    """)

with c4:
    st.markdown("**Field**")
    st.markdown("""
    A named value to extract from the document (e.g. `nama_perniagaan`).
    Uses one of three strategies: Zone, Anchor, or Regex.
    """)

st.divider()

# ── Workflow ──────────────────────────────────────────────────────────────────
st.header("End-to-end workflow")

st.markdown("""
```
1. Create a billing plan          (Actions page)
2. Create a client                (Actions page)
3. Assign plan to client          (Client Detail page)
4. Create a document template     (Templates page)
5. Upload sample image            (Templates page → template detail)
6. Annotate fields                (Annotate page)
7. Grant template to client       (Client Templates page)
8. Hand off API key to client     (Client Detail page)
9. Client integrates the API      (API Reference page)
```
""")

st.divider()

# ── Step-by-step ──────────────────────────────────────────────────────────────
st.header("Step-by-step guide")

# Step 1
with st.expander("Step 1 — Create a billing plan", expanded=False):
    st.markdown("""
    Navigate to **Actions** in the sidebar.

    1. Under **Plans**, fill in:
       - **Name** — e.g. `Standard`
       - **Transaction limit** — number of OCR/verify jobs per billing period
       - **Period days** — billing cycle length (e.g. `30`)
    2. Click **Create Plan**.

    The plan appears in the plans list.  You can create multiple plans
    (e.g. Trial, Standard, Enterprise) and assign different clients to each.
    """)

# Step 2
with st.expander("Step 2 — Create a client", expanded=False):
    st.markdown("""
    Still on the **Actions** page.

    1. Under **Clients**, fill in:
       - **Client name** — human-readable label (e.g. `Acme Corp`)
       - **Notes** — optional context
    2. Click **Create Client**.

    An API key is generated automatically.  You will see it in **Client Detail**.
    """)

# Step 3
with st.expander("Step 3 — Assign a plan to the client", expanded=False):
    st.markdown("""
    Navigate to **Client Detail** and select your client from the dropdown.

    1. Under **Assign Plan**, choose the plan from the dropdown.
    2. Click **Assign**.

    The client can now make API calls up to the plan's transaction limit.
    Quota usage is visible on the same page.
    """)

# Step 4
with st.expander("Step 4 — Create a document template", expanded=False):
    st.markdown("""
    Navigate to **Templates** in the sidebar.

    1. Click **Create new template**.
    2. Fill in:
       - **Name** — human-readable (e.g. `SSM Certificate`)
       - **Doc type code** — short identifier used in API calls (e.g. `sijil_ssm`).
         Use lowercase letters, digits, and underscores only.
    3. Click **Create**.

    The template starts with no fields.  You add fields in the Annotate page.
    """)

# Step 5
with st.expander("Step 5 — Upload a sample image", expanded=False):
    st.markdown("""
    Still on the **Templates** page, open your template.

    1. Click **Upload page image**.
    2. Select a representative sample scan (JPEG or PNG).
       - Use a clean, high-resolution scan.
       - The image defines the coordinate space for Zone fields.
    3. Click **Upload**.

    Multi-page documents: upload one image per page.  Page index starts at 0.
    """)

# Step 6
with st.expander("Step 6 — Annotate fields", expanded=False):
    st.markdown("""
    Navigate to **Annotate** in the sidebar.

    1. Select your template and page from the dropdowns.
    2. Click **Load OCR lines (preview)** — this runs OCR on the sample image
       and overlays the detected text boxes.  Result is cached for the session.
    3. Add fields using one of three methods:

    **Zone field (draw on canvas):**
    - Draw a rectangle around the value area on the image.
    - The matched OCR lines appear in the preview panel.
    - Tune `min_overlap` if the wrong lines are captured.
    - Set field name and post-process, then click **Add zone field**.

    **Anchor or Regex field (paste JSON):**
    - Expand **Edit raw JSON**.
    - Add your field object to the JSON array.
    - Click **Save JSON**.
    - See **Field Strategies Guide** for full JSON reference.

    4. Repeat for each field.
    5. Click **Save** when done.
       - Choose **In-place** to overwrite the current version.
       - Choose **New version** to keep the old version live while testing the new one.

    **Tips:**
    - Click **✕** next to a field card to remove it.
    - Drag-and-drop `display_order` to reorder fields in extraction output.
    - Test extraction immediately using the **Test extraction** panel at the bottom.
    """)

# Step 7
with st.expander("Step 7 — Grant template to client", expanded=False):
    st.markdown("""
    Navigate to **Client Templates** in the sidebar.

    1. Select the client from the dropdown.
    2. Select the template from the **Grant template** dropdown.
    3. Click **Grant**.

    The client's API key can now use `doc_type=<doc_type_code>` in OCR/verify calls.
    You can revoke access at any time by clicking **Revoke** on the granted template row.
    """)

# Step 8
with st.expander("Step 8 — Hand off API credentials", expanded=False):
    st.markdown("""
    Navigate to **Client Detail** and select the client.

    The **API Key** is shown in the details panel.  Share this with the client
    along with:
    - The base URL: `http://173.212.247.3`
    - The `doc_type_code` of the granted template(s)
    - A link to the **API Reference** page for integration examples

    **Security note:** API keys are hashed in the database.  If a key is
    compromised, rotate it via the **Actions** page (Regenerate Key).
    """)

st.divider()

# ── FAQ ───────────────────────────────────────────────────────────────────────
st.header("FAQ")

with st.expander("The OCR is extracting the wrong text for a Zone field."):
    st.markdown("""
    - Increase or decrease `min_overlap` (0.0–1.0).  Default is 0.3.
    - Make the zone larger — OCR line bounding boxes may extend slightly outside
      the visible text.
    - Use `extract_regex` inside the zone config to filter the merged text further.
    - If the document layout varies between scans, switch to an Anchor or Regex field.
    """)

with st.expander("My Anchor field returns nothing."):
    st.markdown("""
    - Check that the label text exactly matches what OCR produces.
      Use **Load OCR lines (preview)** on the Annotate page to see the raw OCR output.
    - Add OCR variants to the `labels` list (e.g. `["NAMA", "NAME", "NEMA"]`).
    - Matching is case-insensitive but must appear somewhere in the OCR line.
    - Try `direction: same_line_colon` first — it is the most robust for label: value layouts.
    """)

with st.expander("My Regex field returns the full match instead of just the value."):
    st.markdown("""
    Wrap the value part in a capture group `(...)` and set `group: 1`.

    Example — to extract just the number from `REG NO: MA0127232-D`:
    ```json
    "pattern": "REG NO[:\\\\s]+(MA\\\\d{7}-[A-Z])",
    "group": 1
    ```
    `group: 0` returns the entire match including the label.
    """)

with st.expander("The verify endpoint returns match: false even though the value looks correct."):
    st.markdown("""
    The comparison normalises both sides before comparing:
    - Strips all whitespace, colons, hyphens, dots, commas
    - Converts to uppercase

    So `DFG TELECOMMUNICATION` == `dfg-telecommunication` == `DFG,TELECOMMUNICATION`.

    If it still fails, check:
    - The extracted value in `all_extracted` — does it contain unexpected characters?
    - Whether post-processing (e.g. `trim`) is stripping too much.
    - Whether the OCR is misreading a character (e.g. `0` vs `O`, `1` vs `I`).
    """)

with st.expander("How do I handle multi-page documents?"):
    st.markdown("""
    Upload one image per page to the template (page index 0, 1, 2...).
    Each field has a `page_index` that tells the engine which page to search.
    The API accepts both JPEG/PNG (single page) and PDF (multi-page) files.
    """)

with st.expander("What happens when a client hits the quota limit?"):
    st.markdown("""
    The API returns HTTP 429 with error code `quota_exceeded`.
    The quota resets automatically at the start of the next billing period.
    To increase the limit, assign the client a higher-tier plan.
    """)

st.divider()

st.markdown("""
**Further reading:**
- [Field Strategies Guide](#) — zone, anchor, regex config reference
- [API Reference](#) — endpoint specs, error codes, code examples
""")
