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
2. Create a document template                 (Templates page → Create tab)
3. Upload sample image                        (Templates page → template detail)
4a. Add anchor / regex / between fields       (Templates page → form editor)
4b. Add zone fields by drawing on the image   (Annotate page → canvas)
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

    Fields can be added later via the **form editor** on the template detail
    (anchor / regex / between), the **JSON textarea** (any strategy), or the
    **Annotate page canvas** (zone strategy only).
    """)

# Step 3
with st.expander("Step 3 — Upload a sample image", expanded=False):
    st.markdown("""
    Still on the **Templates** page, open your template (Browse tab → pick template → Open).

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

# Step 4a
with st.expander("Step 4a — Add anchor / regex / between fields (Templates page form)",
                  expanded=False):
    st.markdown("""
    Open the template (Templates → Browse → pick → Open). Scroll to **Fields**.
    Two columns appear: a **form** on the left and a **draft list + raw JSON**
    on the right. Use the form for anchor / regex / between; use Annotate
    (Step 4b) for zone fields.

    #### Common inputs (every field has these)

    - **Field name** — identifier returned by the API
      (e.g. `nama_perniagaan`). Snake-case recommended.
    - **Page index** — which uploaded page to search (0-based).
      For single-page docs leave as `0`.
    - **Strategy** — pick `anchor`, `regex`, or `between`.
      Switching this swaps the strategy-specific inputs below it.
    - **post_process** — clean-up applied to the extracted value.
      Choices: blank (no clean-up), `trim`, `uppercase`, `lowercase`,
      `number`, `date`. See *Post-process options* in the **Field Strategies Guide**.
    - **required** — if checked, the verify endpoint will fail when this field is missing.
    - **display_order** — controls the order of fields in API responses.
      Lower numbers appear first.

    #### Anchor inputs

    Use when the value sits next to a fixed label (e.g. `NAMA PERNIAGAAN : ...`).

    - **Labels (one per line)** — list of label aliases. The engine tries each
      one until a match is found. Add OCR variants here
      (e.g. `NAMA PERNIAGAAN`, `BUSINESS NAME`).
    - **Direction** — where the value sits relative to the label:
      - `same_line_colon` — same line, after a `:` or `-`
      - `right` — nearest box on the same row to the right
      - `below` — nearest box directly underneath
    - **max_distance_px** — for `right` / `below` only. Maximum pixel
      distance between the label box and the value box. `0` = unlimited.

    #### Regex inputs

    Use when the value matches a unique pattern anywhere on the page
    (registration numbers, dates, amounts).

    - **Pattern** — Python regex. All OCR lines on the page are joined with
      `\\n` before matching, so you can match across line breaks.
    - **Capture group** — `0` returns the full match, `1` returns the first
      `(...)` group, etc. Use `1` with parentheses around the value to
      strip the surrounding text.
    - **ignore_case** — case-insensitive matching (default on).

    #### Between inputs

    Use when the value is a free-form block sandwiched between two known
    phrases (multi-line addresses, descriptions inside paragraphs).

    - **after** — phrase that must appear *before* the value.
      Internal spaces match `\\s+`, so OCR line breaks inside the phrase
      are tolerated.
    - **before** — phrase that must appear *after* the value. Optional —
      leave blank to capture everything from `after` to the end of the page.
    - **ignore_case** — case-insensitive phrase matching (default on).
    - **skip_after tokens (one per line)** — drop these leading words from
      the captured value (e.g. `di` to skip a connector word). Optional.
    - **collapse_whitespace** — if checked (default), runs of whitespace
      including OCR line breaks are replaced with a single space.
      Uncheck only if you need the raw `\\n` between source lines.

    #### Add or update

    1. Fill in the inputs.
    2. Click **Add field** (or **Update field** if you opened a row via ✏).
    3. The field appears in the **Draft fields** list on the right.
    4. The **fields JSON (raw)** textarea below the list reflects the
       current draft. You can also paste / edit JSON there and click
       **Apply JSON to draft** to overwrite the draft from the textarea.

    #### Edit / delete existing fields

    Each row in the draft list has two buttons on the right:

    - **✏** — load the field into the form for editing. The button is
      disabled for `zone` fields (use Annotate page instead).
    - **✕** — remove the field from the draft.

    #### Save

    Scroll to the bottom **Save** section.

    - **New name** — leave blank to keep the current template name.
    - **Save mode**:
      - `In-place (overwrite)` — replace the current version
      - `New version` — keep the old version live while testing the new one
    - Click **Save**.

    A green banner at the top of the page confirms the save.
    """)

# Step 4b
with st.expander("Step 4b — Add zone fields (Annotate page canvas)",
                  expanded=False):
    st.markdown("""
    Navigate to **Annotate** in the sidebar.

    1. Pick the **Template** from the searchable dropdown, then select the
       **Page** from the next dropdown.
    2. Click **Load OCR lines (preview)** — runs OCR on the sample image
       and overlays the detected text boxes. Cached for the session.
    3. **Draw a rectangle** around the value area on the image:
       - The matched OCR lines appear in the preview panel.
       - Tune `min_overlap` if the wrong lines are captured.
       - (Optional) **Pick word(s) to keep** — narrow the capture to a
         single word or contiguous slice.
       - Set field name + post-process, then click **Add zone field**.
    4. Repeat for each zone field.
    5. Click **Save** at the bottom.

    **Tips:**
    - Click **✕** next to a field row to remove it from the draft.
    - To test extraction without hitting the API, use the
      **Test extraction** section on the **Templates** page.
    - For non-zone strategies (anchor / regex / between), use the form
      editor on the Templates page (Step 4a).
    """)

# Step 5
with st.expander("Step 5 — Grant template to client", expanded=False):
    st.markdown("""
    Navigate to **Client Templates** in the sidebar.

    1. Pick the **Client** from the searchable dropdown at the top.
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
