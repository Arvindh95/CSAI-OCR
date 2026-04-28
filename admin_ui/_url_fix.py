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
  const PAGES = new Set([
    'Client_Detail', 'Actions', 'Templates', 'Client_Templates',
    'Annotate', 'Field_Strategies_Guide', 'API_Reference', 'User_Manual'
  ]);
  const clean = () => {
    try {
      const p = w.location.pathname;
      const segs = p.split('/').filter(Boolean);
      if (segs.length < 2) return;
      // Walk from the right; the last segment that names a known page
      // is the user's intended destination. Anything before it is
      // accumulated junk from Streamlit's relative-href navigation.
      let target = null;
      for (let i = segs.length - 1; i >= 0; i--) {
        if (PAGES.has(segs[i])) { target = segs[i]; break; }
      }
      // Also handle the legacy /X/X(/X...)? compounding case.
      if (!target) {
        const allSame = segs.every(s => s === segs[0]);
        if (allSame) target = segs[0];
      }
      if (target && p !== '/' + target) {
        w.history.replaceState(null, '',
          '/' + target + w.location.search + w.location.hash);
      }
    } catch (e) {}
  };
  if (!w.__csaiUrlFixInstalled) {
    const wrap = (fn) => function () {
      const r = fn.apply(this, arguments);
      clean();
      return r;
    };
    w.history.pushState = wrap(w.history.pushState);
    w.history.replaceState = wrap(w.history.replaceState);
    w.addEventListener('popstate', clean);
    w.__csaiUrlFixInstalled = true;
  }
  clean();
} catch (e) {}
</script>
""",
        height=0,
    )
