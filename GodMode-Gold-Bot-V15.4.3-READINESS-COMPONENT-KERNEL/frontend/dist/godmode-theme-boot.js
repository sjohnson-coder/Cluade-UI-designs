/**
 * Resolve the saved theme before the React bundle executes.
 *
 * index.html ships `<html data-theme="dark">` while themeStore used to default to 'light', so a
 * first-time visitor got the dark shell painted from the markup and then watched it flip to light
 * the instant the bundle ran. Both now default to dark, and this file applies the *saved*
 * preference during head parsing so the correct background is on screen from the first frame
 * rather than one repaint later.
 *
 * This is a separate file rather than an inline <script> because the backend serves
 * `script-src 'self'` with no 'unsafe-inline' (app.py security middleware), which is the right
 * policy for an application that can place trades — an inline block here would simply be refused.
 */
(function () {
  try {
    var saved = localStorage.getItem('godmode-theme');
    var mode = (saved === 'light' || saved === 'dark' || saved === 'system') ? saved : 'dark';
    var resolved = mode === 'system'
      ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : mode;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themeMode = mode;
  } catch (e) {
    /* storage blocked (private mode / cookies disabled) — the markup default stands */
  }

  // Promote the font stylesheet from media="print" to media="all" once it has downloaded, so the
  // terminal paints immediately instead of waiting on a third-party round-trip — a locked-down
  // trading VPS with no outbound internet would otherwise stare at nothing until the request timed
  // out. The usual way to write this is an inline onload="" attribute on the <link>, which is an
  // inline script and is refused under script-src 'self'; wiring the listener from here is the
  // CSP-clean equivalent.
  var fonts = document.getElementById('gm-fonts');
  if (fonts) {
    var promote = function () { fonts.media = 'all'; };
    fonts.addEventListener('load', promote, { once: true });
    // If the host is unreachable the load event never fires, so drop the fallback stacks in place
    // rather than leaving a stylesheet permanently scoped to print.
    fonts.addEventListener('error', function () { fonts.remove(); }, { once: true });
    if (fonts.sheet) promote();   // already cached and applied before this script ran
  }
})();
