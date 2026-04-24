"""Client-side URL fix for Streamlit multi-page apps.

Streamlit's sidebar navigation uses relative `./<Page>` links and
`history.pushState`, so clicking a page from `/Page` resolves to
`/Page/Page`, and compounds on further clicks. The nginx 302 only fires
on a full HTTP request, not on pushState. This helper injects a tiny
script that, when it detects /X/X(/X...)? in the top-level URL, replaces
it with /X so the user ends up on the canonical path.
"""
import streamlit.components.v1 as components


def fix_url() -> None:
    components.html(
        """
<script>
try {
  const w = window.parent || window;
  const p = w.location.pathname;
  const m = p.match(/^\\/([^/]+)(?:\\/\\1)+\\/?$/);
  if (m) { w.history.replaceState(null, '', '/' + m[1] + w.location.search + w.location.hash); }
} catch (e) {}
</script>
""",
        height=0,
    )
