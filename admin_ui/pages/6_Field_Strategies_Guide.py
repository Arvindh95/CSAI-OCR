import streamlit as st

st.set_page_config(page_title="Field Strategies Guide", layout="wide")
st.title("Field Extraction Strategies Guide")

st.markdown("""
Use this guide to understand the three extraction strategies available when
building templates.  You can **mix strategies** in a single template -- use
whichever fits each field best.

---
""")

# ── Zone ──────────────────────────────────────────────────────────────────────
st.header("1. Zone (visual annotation)")
st.markdown("""
**How it works:** Draw a rectangle on the template image.  Any OCR line whose
bounding box overlaps the zone by at least `min_overlap` is captured.

**Best for:** Fixed-layout documents where the field is always in the same
position (e.g. SSM certificates, government forms).

**How to add:** Draw on the canvas in the **Annotate** page, or paste JSON.
""")

with st.expander("Zone config reference"):
    st.json({
        "name": "no_pendaftaran",
        "page_index": 0,
        "strategy": "zone",
        "config": {
            "x": 248, "y": 236, "w": 73, "h": 15,
            "merge": True,
            "min_overlap": 0.3,
            "_comment_merge": "true = join multi-line text in zone",
            "_comment_min_overlap": "0.0 - 1.0, how much of the OCR line must be inside the zone",
        },
        "post_process": "trim",
        "required": True,
        "display_order": 0,
    })

with st.expander("Zone: extract specific words"):
    st.markdown("""
    Sometimes the zone captures a full line but you only want part of it.

    **`word_index`** -- pick a single word by position (0-based):
    ```json
    "config": {"x":100, "y":200, "w":500, "h":30, "word_index": 2}
    ```
    If OCR text = `"NAMA : DFG TELECOMMUNICATION"`, word 2 = `"DFG"`.

    **`word_slice`** -- pick a range of words `[start, end)`:
    ```json
    "config": {"x":100, "y":200, "w":500, "h":30, "word_slice": [2, 5]}
    ```
    Words 2-4 = `"DFG TELECOMMUNICATION"` (if 3 words).

    **`extract_regex`** -- regex on the merged text:
    ```json
    "config": {"x":100, "y":200, "w":500, "h":30, "extract_regex": ":\\\\s*(.+)"}
    ```
    Captures everything after the colon.
    """)

st.divider()

# ── Anchor ────────────────────────────────────────────────────────────────────
st.header("2. Anchor (label-based)")
st.markdown("""
**How it works:** Find a known label in the OCR text (e.g. "NAMA PERNIAGAAN"),
then extract the value **relative** to it (right, below, or same line after colon).

**Best for:** Semi-structured documents where labels are consistent but the
layout may shift between scans.

**How to add:** Paste JSON in the "Edit raw JSON" box on the Annotate page.
""")

st.subheader("Directions")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**`same_line_colon`**")
    st.markdown("""
    Finds the label on any line, extracts everything after `:` or `-` on that
    same line.

    Example OCR line:
    `"NAMA PERNIAGAAN : DFG TELECOMMUNICATION"`

    Extracts: `DFG TELECOMMUNICATION`
    """)
    st.json({
        "name": "nama_perniagaan",
        "page_index": 0,
        "strategy": "anchor",
        "config": {
            "labels": ["NAMA PERNIAGAAN"],
            "direction": "same_line_colon",
        },
        "post_process": "trim",
        "required": True,
        "display_order": 0,
    })

with col2:
    st.markdown("**`right`**")
    st.markdown("""
    Finds the label, then looks for the nearest text to the **right** of it
    (on the same horizontal line, within `max_distance_px`).

    Use when label and value are in separate OCR boxes on the same row.
    """)
    st.json({
        "name": "nama_perniagaan",
        "page_index": 0,
        "strategy": "anchor",
        "config": {
            "labels": ["NAMA PERNIAGAAN"],
            "direction": "right",
            "max_distance_px": 300,
        },
        "post_process": "trim",
        "required": True,
        "display_order": 0,
    })

with col3:
    st.markdown("**`below`**")
    st.markdown("""
    Finds the label, then looks for the nearest text **below** it
    (within `max_distance_px` horizontally and vertically).

    Use when the value is on the next line under the label.
    """)
    st.json({
        "name": "address",
        "page_index": 0,
        "strategy": "anchor",
        "config": {
            "labels": ["ALAMAT"],
            "direction": "below",
            "max_distance_px": 200,
        },
        "post_process": "trim",
        "required": False,
        "display_order": 2,
    })

with st.expander("Anchor: multiple labels (aliases)"):
    st.markdown("""
    The `labels` field is a **list** -- the engine tries each one until it finds
    a match.  This handles OCR variations or multilingual labels:

    ```json
    "labels": ["NAMA PERNIAGAAN", "BUSINESS NAME", "NAMA SYARIKAT"]
    ```

    Matching is **case-insensitive** and checks if the label appears **anywhere**
    in the OCR line text.
    """)

st.divider()

# ── Regex ─────────────────────────────────────────────────────────────────────
st.header("3. Regex (pattern matching)")
st.markdown("""
**How it works:** All OCR lines on the page are joined with newlines into one
big string.  Your regex pattern is searched against that string.

**Best for:** Fields with a unique, recognizable pattern regardless of position
(registration numbers, dates, amounts, emails, etc.).

**How to add:** Paste JSON in the "Edit raw JSON" box on the Annotate page.
""")

st.subheader("Examples")

ex1, ex2, ex3, ex4 = st.columns(4)

with ex1:
    st.markdown("**Extract registration number**")
    st.markdown("Pattern: `MA\\d{7}-[A-Z]`")
    st.markdown("Matches: `MA0127232-D`")
    st.json({
        "name": "no_pendaftaran",
        "page_index": 0,
        "strategy": "regex",
        "config": {
            "pattern": "(MA\\d{7}-[A-Z])",
            "group": 1,
            "ignore_case": False,
        },
        "post_process": None,
        "required": True,
        "display_order": 0,
    })

with ex2:
    st.markdown("**Extract text after a keyword**")
    st.markdown("Pattern: `NAMA PERNIAGAAN[\\s:]+(.+)`")
    st.markdown("Captures everything after the label.")
    st.json({
        "name": "nama_perniagaan",
        "page_index": 0,
        "strategy": "regex",
        "config": {
            "pattern": "NAMA PERNIAGAAN[\\s:]+(.+)",
            "group": 1,
            "ignore_case": True,
        },
        "post_process": "trim",
        "required": True,
        "display_order": 1,
    })

with ex3:
    st.markdown("**Extract date in DD-MM-YYYY format**")
    st.markdown("Pattern: `(\\d{2}-\\d{2}-\\d{4})`")
    st.markdown("First date found on the page.")
    st.json({
        "name": "tarikh",
        "page_index": 0,
        "strategy": "regex",
        "config": {
            "pattern": "(\\d{2}-\\d{2}-\\d{4})",
            "group": 1,
        },
        "post_process": "date",
        "required": False,
        "display_order": 2,
    })

with ex4:
    st.markdown("**Extract text between two keywords**")
    st.markdown("Pattern: `KEYWORD1(.*?)KEYWORD2`")
    st.markdown("Captures text sandwiched between two labels. Use `[\\\\s\\\\S]*?` to span multiple lines.")
    st.json({
        "name": "modal_berbayar",
        "page_index": 0,
        "strategy": "regex",
        "config": {
            "pattern": "MODAL BERBAYAR[\\s:]+([\\s\\S]*?)(?=TARIKH|$)",
            "group": 1,
            "ignore_case": True,
        },
        "post_process": "trim",
        "required": False,
        "display_order": 3,
    })

with st.expander("Regex config reference"):
    st.markdown("""
    | Key | Type | Default | Description |
    |-----|------|---------|-------------|
    | `pattern` | string | *required* | Python regex pattern |
    | `group` | int | `0` | Which capture group to return (0 = full match, 1 = first group) |
    | `ignore_case` | bool | `true` | Case-insensitive matching |

    **Tips:**
    - Use `group: 1` with parentheses `(...)` to capture only the value you want
    - All OCR lines on the page are joined with `\\n`, so you can match across lines
    - Double-escape backslashes in JSON: `\\\\d` for `\\d`
    - Test your regex at [regex101.com](https://regex101.com/) (select Python flavor)
    """)

st.divider()

# ── Post-process ──────────────────────────────────────────────────────────────
st.header("Post-process options")
st.markdown("""
Applied **after** extraction to clean up the value.

| Option | What it does | Example |
|--------|-------------|---------|
| `trim` | Strip leading/trailing `: - —` and whitespace | `: DFG TELCO` -> `DFG TELCO` |
| `uppercase` | Trim + convert to uppercase | `dfg telco` -> `DFG TELCO` |
| `lowercase` | Trim + convert to lowercase | `DFG TELCO` -> `dfg telco` |
| `number` | Extract numeric value, strip non-digits | `RM 1,234.50` -> `1234.5` |
| `date` | Parse date string to ISO format | `08-09-2008` -> `2008-09-08` |
| `strip_chars:X` | Strip specific characters from start/end | `strip_chars::` strips colons |
""")

st.divider()

# ── Decision flowchart ────────────────────────────────────────────────────────
st.header("Which strategy to use?")
st.markdown("""
```
Is the field always in the same position on the page?
  YES -> Use ZONE (draw on canvas)
  NO  -> Does the field have a recognizable label next to it?
           YES -> Use ANCHOR (label + direction)
           NO  -> Does the field have a unique pattern (number, date, code)?
                    YES -> Use REGEX (pattern match)
                    NO  -> Use ZONE with a large box + extract_regex
```
""")

st.divider()

# ── Full template example ─────────────────────────────────────────────────────
st.header("Full template example (mixed strategies)")
st.markdown("Copy this into the raw JSON editor on the Annotate page:")

st.json([
    {
        "name": "no_pendaftaran",
        "page_index": 0,
        "strategy": "regex",
        "config": {"pattern": "(MA\\d{7}-[A-Z])", "group": 1},
        "post_process": None,
        "required": True,
        "display_order": 0,
    },
    {
        "name": "nama_perniagaan",
        "page_index": 0,
        "strategy": "anchor",
        "config": {"labels": ["NAMA PERNIAGAAN"], "direction": "same_line_colon"},
        "post_process": "trim",
        "required": True,
        "display_order": 1,
    },
    {
        "name": "alamat",
        "page_index": 0,
        "strategy": "zone",
        "config": {"x": 247, "y": 258, "w": 400, "h": 80, "merge": True, "min_overlap": 0.3},
        "post_process": "trim",
        "required": False,
        "display_order": 2,
    },
    {
        "name": "tarikh_pendaftaran",
        "page_index": 0,
        "strategy": "regex",
        "config": {"pattern": "TARIKH PENDAFTARAN[\\s:]+([\\d-]+)", "group": 1},
        "post_process": "date",
        "required": False,
        "display_order": 3,
    },
    {
        "name": "status",
        "page_index": 0,
        "strategy": "anchor",
        "config": {"labels": ["STATUS"], "direction": "same_line_colon"},
        "post_process": "uppercase",
        "required": False,
        "display_order": 4,
    },
])

st.divider()

st.info("For API endpoints, request/response formats, and code examples — see the **API Reference** page in the sidebar.")
