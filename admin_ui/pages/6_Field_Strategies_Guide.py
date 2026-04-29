import streamlit as st

from admin_ui._url_fix import fix_url

st.set_page_config(page_title="Field Strategies Guide", layout="wide")
fix_url()
st.title("Field Extraction Strategies Guide")

st.markdown("""
Use this guide to understand the four extraction strategies available when
building templates.  You can **mix strategies** in a single template -- use
whichever fits each field best.

> **How to add fields**
> - **Anchor / Regex / Between** → use the **form editor** on the Templates
>   page (template detail → *Fields* section).  The form generates the
>   exact JSON shapes shown below.
> - **Zone** → draw on the canvas on the **Annotate** page.
> - Either way, you can also paste raw JSON into the *fields JSON (raw)*
>   textarea and click *Apply JSON to draft*.

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

with st.expander("Zone: worked example"):
    st.markdown("""
    **Scenario:** Extract the registration number from an SSM certificate.
    The number always appears at the same position on every certificate.

    **OCR lines on the page — zone drawn tightly around the number:**
    """)
    st.markdown("""
<div style="background:#1e1e2e;border:1px solid #444;border-radius:6px;padding:16px;font-family:monospace;font-size:13px;">
  <div style="position:relative;background:#111827;border:1px solid #374151;border-radius:4px;padding:0;height:108px;overflow:visible;">
    <div style="position:absolute;top:10px;left:20px;color:#555;font-size:12px;">NO. PENDAFTARAN</div>
    <div style="position:absolute;top:32px;left:106px;width:84px;height:38px;border:2px dashed #f59e0b;border-radius:3px;background:rgba(245,158,11,0.08);">
      <div style="position:absolute;top:-16px;left:0;color:#f59e0b;font-size:10px;white-space:nowrap;">▶ zone (x=248, y=236, w=73, h=15)</div>
    </div>
    <div style="position:absolute;top:42px;left:108px;color:#4ade80;font-weight:bold;font-size:12px;background:rgba(74,222,128,0.12);padding:2px 8px;border-radius:2px;">MA0127232-D</div>
    <div style="position:absolute;top:80px;left:20px;color:#555;font-size:12px;">TARIKH PENDAFTARAN</div>
  </div>
  <div style="margin-top:10px;font-size:11px;color:#888;">
    <span style="color:#f59e0b;">- -</span> zone boundary &nbsp;&nbsp;
    <span style="color:#4ade80;">■</span> captured (overlaps zone ≥ 30%) &nbsp;&nbsp;
    <span style="color:#555;">■</span> excluded
  </div>
</div>
""", unsafe_allow_html=True)
    st.markdown("**Overlap check:** the `MA0127232-D` bbox overlaps the zone by >30% → captured.")
    st.json({
        "name": "no_pendaftaran",
        "strategy": "zone",
        "config": {"x": 248, "y": 236, "w": 73, "h": 15, "merge": True, "min_overlap": 0.3},
        "post_process": "trim",
    })
    st.success("Extracted → `MA0127232-D`")
    st.markdown("""
    **What if the zone also catches the label line above?**
    Raise `min_overlap` to `0.6` — the label line only overlaps the zone by ~10%, so it gets filtered out.
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

with st.expander("Anchor: worked examples"):
    st.markdown("#### `same_line_colon`")
    st.markdown("**OCR returns one box containing the full line:**")
    st.markdown("""
<div style="background:#1e1e2e;border:1px solid #444;border-radius:6px;padding:14px 16px;font-family:monospace;font-size:13px;line-height:2.2;">
  <div style="color:#666;">SIJIL PENDAFTARAN PERNIAGAAN</div>
  <div style="border:1px solid #555;background:#2a2a3e;padding:4px 10px;border-radius:4px;display:inline-block;margin:2px 0;">
    <span style="color:#f59e0b;font-weight:bold;">NAMA PERNIAGAAN</span>
    <span style="color:#888;"> : </span>
    <span style="color:#4ade80;font-weight:bold;">DFG TELECOMMUNICATION SDN BHD</span>
  </div>
  <div style="color:#666;">NO. PENDAFTARAN : MA0127232-D</div>
  <div style="color:#666;">TARIKH PENDAFTARAN : 08-09-2008</div>
  <div style="color:#666;">STATUS : AKTIF</div>
  <div style="margin-top:8px;font-size:11px;color:#888;">
    <span style="color:#f59e0b;">■</span> anchor label &nbsp;&nbsp;
    <span style="color:#4ade80;">■</span> extracted value
  </div>
</div>
""", unsafe_allow_html=True)
    st.json({
        "name": "nama_perniagaan",
        "strategy": "anchor",
        "config": {"labels": ["NAMA PERNIAGAAN"], "direction": "same_line_colon"},
        "post_process": "trim",
    })
    st.success("Extracted → `DFG TELECOMMUNICATION SDN BHD`")
    st.caption("Engine finds the line containing 'NAMA PERNIAGAAN', then captures everything after the ':'.")

    st.divider()

    st.markdown("#### `right`")
    st.markdown("**OCR returns two separate boxes on the same row** (common in table-style layouts):")
    st.markdown("""
<div style="background:#1e1e2e;border:1px solid #444;border-radius:6px;padding:16px;font-family:monospace;font-size:13px;">
  <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
    <div style="border:2px solid #f59e0b;background:#2a2010;padding:8px 14px;border-radius:4px;">
      <div style="color:#f59e0b;font-size:10px;margin-bottom:2px;">anchor label</div>
      <div style="color:#fde68a;">NAMA PERNIAGAAN</div>
    </div>
    <div style="font-size:22px;color:#888;">→</div>
    <div style="border:2px solid #4ade80;background:#0f2a1a;padding:8px 14px;border-radius:4px;">
      <div style="color:#4ade80;font-size:10px;margin-bottom:2px;">extracted value</div>
      <div style="color:#bbf7d0;">DFG TELECOMMUNICATION</div>
    </div>
    <div style="color:#666;font-size:11px;align-self:flex-end;">≈ 110 px gap (within max_distance_px=300)</div>
  </div>
</div>
""", unsafe_allow_html=True)
    st.json({
        "name": "nama_perniagaan",
        "strategy": "anchor",
        "config": {"labels": ["NAMA PERNIAGAAN"], "direction": "right", "max_distance_px": 300},
        "post_process": "trim",
    })
    st.success("Extracted → `DFG TELECOMMUNICATION`")
    st.caption("Engine finds 'NAMA PERNIAGAAN', then picks the nearest box to its right within 300 px.")

    st.divider()

    st.markdown("#### `below`")
    st.markdown("**OCR returns each line as a separate box stacked vertically** (common in address blocks):")
    st.markdown("""
<div style="background:#1e1e2e;border:1px solid #444;border-radius:6px;padding:16px;font-family:monospace;font-size:13px;">
  <div style="display:flex;flex-direction:column;align-items:flex-start;gap:4px;">
    <div style="border:2px solid #f59e0b;background:#2a2010;padding:8px 14px;border-radius:4px;">
      <div style="color:#f59e0b;font-size:10px;margin-bottom:2px;">anchor label</div>
      <div style="color:#fde68a;">ALAMAT BERDAFTAR</div>
    </div>
    <div style="font-size:20px;color:#888;margin-left:24px;">↓</div>
    <div style="border:2px solid #4ade80;background:#0f2a1a;padding:8px 14px;border-radius:4px;">
      <div style="color:#4ade80;font-size:10px;margin-bottom:2px;">extracted value (nearest below)</div>
      <div style="color:#bbf7d0;">NO. 5, JALAN KENANGA 1/1</div>
    </div>
    <div style="border:1px dashed #444;background:#1a1a2a;padding:8px 14px;border-radius:4px;color:#555;">
      41200 KLANG, SELANGOR &nbsp;<em style="font-size:11px;">(further away — not captured)</em>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)
    st.json({
        "name": "alamat",
        "strategy": "anchor",
        "config": {"labels": ["ALAMAT BERDAFTAR"], "direction": "below", "max_distance_px": 200},
        "post_process": "trim",
    })
    st.success("Extracted → `NO. 5, JALAN KENANGA 1/1`")
    st.caption("Engine finds 'ALAMAT BERDAFTAR', then picks the nearest line directly below it.")

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

with st.expander("Regex: worked examples"):
    st.markdown("**All OCR lines on the page are joined into one string before matching:**")
    st.code(
        "SURUHANJAYA SYARIKAT MALAYSIA\n"
        "SIJIL PENDAFTARAN PERNIAGAAN\n"
        "NAMA PERNIAGAAN : DFG TELECOMMUNICATION SDN BHD\n"
        "NO. PENDAFTARAN : MA0127232-D\n"
        "TARIKH PENDAFTARAN : 08-09-2008\n"
        "MODAL BERBAYAR : RM 50,000.00\n"
        "STATUS : AKTIF",
        language=None,
    )

    st.divider()

    r1, r2 = st.columns(2)

    with r1:
        st.markdown("**Example 1 — Extract registration number**")
        st.markdown("Pattern: `(MA\\d{7}-[A-Z])` · group: `1`")
        st.json({
            "config": {"pattern": "(MA\\d{7}-[A-Z])", "group": 1, "ignore_case": False},
        })
        st.success("Extracted → `MA0127232-D`")

        st.markdown("**Example 2 — Extract date**")
        st.markdown("Pattern: `(\\d{2}-\\d{2}-\\d{4})` · group: `1` · post_process: `date`")
        st.json({
            "config": {"pattern": "(\\d{2}-\\d{2}-\\d{4})", "group": 1},
            "post_process": "date",
        })
        st.success("Extracted → `2008-09-08`")

    with r2:
        st.markdown("**Example 3 — Extract text after keyword**")
        st.markdown("Pattern: `NAMA PERNIAGAAN[\\s:]+(.+)` · group: `1`")
        st.json({
            "config": {"pattern": "NAMA PERNIAGAAN[\\s:]+(.+)", "group": 1, "ignore_case": True},
            "post_process": "trim",
        })
        st.success("Extracted → `DFG TELECOMMUNICATION SDN BHD`")

        st.markdown("**Example 4 — Extract currency amount**")
        st.markdown("Pattern: `MODAL BERBAYAR[\\s:]+RM\\s*([\\d,\\.]+)` · group: `1` · post_process: `number`")
        st.json({
            "config": {
                "pattern": "MODAL BERBAYAR[\\s:]+RM\\s*([\\d,\\.]+)",
                "group": 1,
                "ignore_case": True,
            },
            "post_process": "number",
        })
        st.success("Extracted → `50000.0`")

st.divider()

# ── Between ───────────────────────────────────────────────────────────────────
st.header("4. Between (sentence anchors)")
st.markdown("""
**How it works:** Capture all text **after** one phrase and (optionally) **before**
another. Phrases match across OCR line breaks — internal spaces become flexible
whitespace, so an OCR break like `tempat utama\\nperniagaannya` still matches
the phrase `"tempat utama perniagaannya"`.

**Best for:** Multi-line free-form blocks bracketed by known sentences — e.g.
addresses inside a paragraph, descriptions between two section headers.

**vs Anchor:** anchor returns a *single* OCR line.  `between` returns
*everything* between the two anchor phrases (multi-line OK).

**vs Regex:** same idea, but you write phrases instead of regex.  No escaping,
no `[\\s\\S]+?` tricks — friendlier when the content can contain `.` `,` etc.
""")

with st.expander("Between config reference"):
    st.markdown("""
    | Key | Type | Default | Description |
    |-----|------|---------|-------------|
    | `after` | string | *required* | Phrase that must appear **before** the value |
    | `before` | string | *(optional)* | Phrase that must appear **after** the value. Omit to capture to end of page. |
    | `ignore_case` | bool | `true` | Case-insensitive phrase matching |
    | `skip_after` | list | `[]` | Drop these leading tokens from the captured value (e.g. `["di"]` to skip a connector word) |
    | `collapse_whitespace` | bool | `true` | Replace any run of whitespace (including OCR-line `\\n`) with a single space, so multi-line captures come back as one clean line. Set `false` to keep `\\n` between source lines. |

    **Tip:** keep `after` specific enough that it appears **only once** on the page.
    """)

with st.expander("Between: worked example — SSM address paragraph"):
    st.markdown("**OCR lines (joined into one string with newlines):**")
    st.code(
        "Dengan ini diperakui bahawa Perniagaan yang dijalankan dengan nama\n"
        "KEDAI RUNCIT MAJU JAYA\n"
        "telah didaftarkan dari hari ini sehingga 31 MEI 2012 menurut peruntukan-\n"
        "peruntukan Akta Pendaftaran Perniagaan 1956, dengan nombor yang ditunjukkan\n"
        "di sini dan tempat utama perniagaannya NO. 49, JALAN KHABAR HIDUP\n"
        "42, TAMAN PERUNDING 5, 41000, KLANG, NEGERI SEMBILAN.\n"
        "Jenis Perniagaan\n"
        "MENJUAL DAN MEMBEKAL ...",
        language=None,
    )
    st.json({
        "name": "alamat_perniagaan",
        "page_index": 0,
        "strategy": "between",
        "config": {
            "after": "tempat utama perniagaannya",
            "before": "Jenis Perniagaan",
            "skip_after": ["di"],
        },
        "post_process": "trim",
        "required": True,
        "display_order": 2,
    })
    st.success("Extracted → `NO. 49, JALAN KHABAR HIDUP\\n42, TAMAN PERUNDING 5, 41000, KLANG, NEGERI SEMBILAN.`")
    st.caption("`after` and `before` are matched case-insensitively. Internal spaces in each phrase become "
               "`\\s+` so OCR line breaks inside the phrase don't break the match.")

with st.expander("Between: capture to end of page"):
    st.markdown("Omit `before` to grab everything after the anchor:")
    st.json({
        "name": "footer_block",
        "strategy": "between",
        "config": {"after": "Disahkan oleh"},
        "post_process": "trim",
    })

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

with st.expander("Post-process: worked examples"):
    st.markdown("Same raw extracted value `': DFG TELECOMMUNICATION SDN BHD '` — different post_process applied:")

    pp1, pp2, pp3 = st.columns(3)
    with pp1:
        st.markdown("**`trim`**")
        st.code(": DFG TELECOMMUNICATION SDN BHD ", language=None)
        st.markdown("↓")
        st.success("DFG TELECOMMUNICATION SDN BHD")

    with pp2:
        st.markdown("**`uppercase`**")
        st.code(": dfg telecommunication sdn bhd", language=None)
        st.markdown("↓")
        st.success("DFG TELECOMMUNICATION SDN BHD")

    with pp3:
        st.markdown("**`lowercase`**")
        st.code(": DFG TELECOMMUNICATION SDN BHD", language=None)
        st.markdown("↓")
        st.success("dfg telecommunication sdn bhd")

    st.divider()

    pp4, pp5, pp6 = st.columns(3)
    with pp4:
        st.markdown("**`number`**")
        st.code("RM 1,234.50", language=None)
        st.markdown("↓")
        st.success("1234.5")

    with pp5:
        st.markdown("**`date`**")
        st.code("08-09-2008", language=None)
        st.markdown("↓")
        st.success("2008-09-08")
        st.caption("Also parses: `08/09/2008`, `08 Sep 2008`, `2008/09/08`")

    with pp6:
        st.markdown("**`strip_chars::`**")
        st.code(":AKTIF:", language=None)
        st.markdown("↓")
        st.success("AKTIF")
        st.caption("Strips only the specified char(s) from both ends.")

st.divider()

# ── Decision flowchart ────────────────────────────────────────────────────────
st.header("Which strategy to use?")
st.markdown("""
```
Is the field always in the same position on the page?
  YES -> Use ZONE (draw on canvas)
  NO  -> Is the field a multi-line block sandwiched between two known sentences?
           YES -> Use BETWEEN (after / before phrases)
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
