import streamlit as st

from admin_ui._url_fix import fix_url

st.set_page_config(page_title="User Manual", layout="wide")
fix_url()
st.title("User Manual")

st.markdown("""
This manual covers the full admin workflow — from onboarding a client to annotating
templates and handing off API credentials.

---
""")

# ── Concepts ──────────────────────────────────────────────────────────────────
st.header("Key concepts")

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("**Client**")
    st.markdown("""
    An organisation or system that consumes the OCR API.
    Each client has an API key and a quota plan (set at creation, editable anytime).
    """)

with c2:
    st.markdown("**Template**")
    st.markdown("""
    A document type definition (e.g. `sijil_ssm`). Contains one or more
    fields, each with an extraction strategy and optional post-processing.
    """)

with c3:
    st.markdown("**Field**")
    st.markdown("""
    A named value to extract from the document (e.g. `nama_perniagaan`).
    Uses one of four strategies: Zone, Anchor, Regex, or Between.
    """)

st.divider()

# ── Workflow ──────────────────────────────────────────────────────────────────
st.header("End-to-end workflow")

st.markdown("""
```
1. Create a client (plan settings included)   (Actions page)
2. Create a document template                 (Templates page)
3. Upload sample image                        (Templates page → template detail)
4. Annotate fields                            (Annotate page)
5. Grant template to client                   (Client Templates page)
6. Hand off API key to client                 (shown once at creation)
7. Client integrates the API                  (API Reference page)
```
""")

st.divider()

# ── Step-by-step ──────────────────────────────────────────────────────────────
st.header("Step-by-step guide")

# Step 1
with st.expander("Step 1 — Create a client", expanded=False):
    st.markdown("""
    Navigate to **Actions** in the sidebar.

    Fill in the **Create client** form:
    - **Name** — human-readable label (e.g. `Acme Corp`)
    - **Email** — contact email for the client
    - **Max transactions** — OCR/verify job quota per billing period
    - **Max pages / txn** — maximum pages allowed per single job
    - **Reset period** — `monthly` (resets each month) or `lifetime` (never resets)

    Click **Create**.

    The API key is shown **once** immediately after creation — copy it now.
    The client's plan is set from these same fields; you can update it later
    under **Plan upsert** on the same page.
    """)

# Step 2
with st.expander("Step 2 — Create a document template", expanded=False):
    st.markdown("""
    Navigate to **Templates** in the sidebar.

    1. Click the **Create** tab.
    2. Fill in:
       - **Name** — human-readable (e.g. `SSM Certificate`)
       - **Doc type code** — short identifier used in API calls (e.g. `sijil_ssm`).
         Allowed: lowercase letters, digits, underscores, hyphens.
       - **Scope** — `global` (available to all clients) or `client-specific`
    3. Optionally edit the pre-filled **fields** JSON, or leave it and edit later.
    4. Click **Create**.

    Fields can be added or edited here (fields JSON textarea) or visually in the Annotate page.
    """)

# Step 3
with st.expander("Step 3 — Upload a sample image", expanded=False):
    st.markdown("""
    Still on the **Templates** page, open your template (Browse tab → enter ID → Open).

    Under **Sample pages**:
    1. Set **Page index** (0-based — first page = 0).
    2. Upload a representative sample scan (JPEG or PNG).
       - Use a clean, high-resolution scan.
       - The image defines the coordinate space for Zone fields.
    3. Click **Upload page**.

    Multi-page documents: repeat for each page, incrementing the page index.

    You can also **Test extraction** here — upload a test document and click **Run test**
    to see extracted fields without going through the API.
    """)

# Step 4
with st.expander("Step 4 — Annotate fields", expanded=False):
    st.markdown("""
    Navigate to **Annotate** in the sidebar.

    1. Enter the **Template ID** in the number input at the top, then select the **Page** from the dropdown.
    2. Click **Load OCR lines (preview)** — this runs OCR on the sample image
       and overlays the detected text boxes.  Result is cached for the session.
    3. Add fields using one of four methods:

    **Zone field (draw on canvas):**
    - Draw a rectangle around the value area on the image.
    - The matched OCR lines appear in the preview panel.
    - Tune `min_overlap` if the wrong lines are captured.
    - Set field name and post-process, then click **Add zone field**.

    **Anchor / Regex / Between field (edit raw JSON):**
    - Scroll down to the **Edit raw JSON (optional)** textarea.
    - Add your field object to the JSON array.
    - Click **Apply JSON to draft** to update the draft fields list.
    - See **Field Strategies Guide** for full JSON reference.
    - Use **Between** when the value is a multi-line block bracketed by two
      known sentences (e.g. an address paragraph between two section headers).

    4. Repeat for each field.
    5. Click **Save** when done.
       - Choose **In-place (overwrite)** to overwrite the current version.
       - Choose **New version** to keep the old version live while testing the new one.

    **Tips:**
    - Click **✕** next to a field row to remove it from the draft.
    - Change `display_order` (number input on the field form) to control output ordering.
    - To test extraction without hitting the API, use the **Test extraction** section on the **Templates** page.
    """)

# Step 5
with st.expander("Step 5 — Grant template to client", expanded=False):
    st.markdown("""
    Navigate to **Client Templates** in the sidebar.

    1. Enter the **Client ID** in the number input at the top.
    2. Under **Grant a template**, select the template from the dropdown.
    3. Click **Grant**.

    The client's API key can now use `doc_type=<doc_type_code>` in OCR/verify calls.
    You can revoke access at any time by clicking **Revoke** on the granted template row.
    """)

# Step 6
with st.expander("Step 6 — Hand off API credentials", expanded=False):
    st.markdown("""
    The API key was shown once when you created the client (Step 1).

    Share with the client:
    - The API key
    - The base URL: `http://173.212.247.3`
    - The `doc_type_code` of the granted template(s)
    - A link to the **API Reference** page for integration examples

    **If the key was not saved:** rotate it via **Actions** → **Rotate API key**.
    The new key is shown once immediately after rotation.
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
    - If the document layout varies between scans, switch to an Anchor, Regex, or Between field.
    """)

with st.expander("My Anchor field returns nothing."):
    st.markdown("""
    - Check that the label text exactly matches what OCR produces.
      Use **Load OCR lines (preview)** on the Annotate page to see the raw OCR output.
    - Add OCR variants to the `labels` list (e.g. `["NAMA", "NAME", "NEMA"]`).
    - Matching is case-insensitive but must appear somewhere in the OCR line.
    - Try `direction: same_line_colon` first — it is the most robust for label: value layouts.
    """)

with st.expander("My Between field returns nothing or the wrong text."):
    st.markdown("""
    - The **`after`** phrase must appear on the page; OCR may have split or
      misread it. Use **Load OCR lines (preview)** on the Annotate page to
      see the raw OCR output and adjust the phrase to match what OCR really
      returned.
    - If the captured value also contains the next section, the **`before`**
      phrase is wrong or missing. Pick a sentence that always follows the
      block you want.
    - Internal spaces in `after`/`before` are matched as `\\s+`, so OCR line
      breaks inside the phrase are tolerated automatically.
    - Make `after` specific enough that it occurs **only once** on the page —
      otherwise the regex matches the first occurrence, which may be wrong.
    - Set `collapse_whitespace: false` if you actually want `\\n` preserved
      between the original OCR lines (default collapses them to single space).
    - Use `skip_after: ["di"]` (or any other connector words) to drop a
      leading filler token from the captured value.
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
    - Converts to **lowercase**
    - Strips all whitespace, colons, hyphens, en/em-dashes, dots, commas, semicolons

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
    For `monthly` plans, quota resets automatically at the start of the next billing period.
    For `lifetime` plans, quota never resets — you must raise the limit or it stays exhausted.
    To increase the limit, go to **Actions** → **Plan upsert** and raise **Max transactions**.
    """)

st.divider()

st.markdown("""
**Further reading:**
- [Field Strategies Guide](#) — zone, anchor, regex, between config reference
- [API Reference](#) — endpoint specs, error codes, code examples
""")
