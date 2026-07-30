/**
 * GodMode runtime bus — shared, coalesced JSON reads for the non-module runtime scripts.
 *
 * WHY THIS EXISTS
 * ---------------
 * Five independent consumers poll this backend from one browser tab: the React shell, the React
 * Dashboard page, and the predictor-live / burst-live / runtime-recovery scripts loaded from
 * index.html. None of them knew about the others, so the measured steady state was roughly
 * 6.5 requests per second, with two endpoints fetched twice per second by two different code
 * paths asking the same question at the same moment:
 *
 *     /api/fast-sniper/status                      React Dashboard @1Hz  +  predictor-live @1Hz
 *     /api/trading-modes/protected-burst/status    React Dashboard @1Hz  +  burst-live     @1Hz
 *     /api/readiness                               React App @8s         +  runtime-recovery @1Hz
 *
 * Every one of those hits a synchronous FastAPI handler running in a bounded thread pool, so the
 * duplication was not free — it directly contended with the trading loop for the GIL.
 *
 * This module installs window.__godmodeFetchJSON(path, ttlMs). Concurrent callers for the same
 * path share a single in-flight request, and a short TTL absorbs the common case where two timers
 * fire a few milliseconds apart rather than simultaneously. src/lib/api.ts installs a version
 * backed by the React app's own request pipeline (timeouts, API key, offline fallbacks) and takes
 * precedence when it loads; this file is the standalone fallback so the runtime scripts still work
 * if the bundle has not executed yet, or fails to.
 *
 * It also exports __godmodeRenderOnce(el, html), which skips the DOM write when the markup is
 * unchanged. The runtime panels each did `el.innerHTML = ...` on a 1s interval forever, which
 * reparses and rebuilds a subtree every second whether or not anything moved — and destroys text
 * selection and focus inside those panels every time.
 */
(function () {
  'use strict';

  // Installed unconditionally: it touches no network state, and returning early when api.ts has
  // already provided __godmodeFetchJSON would leave the runtime panels without a change check and
  // back on the per-second innerHTML rewrite this exists to remove.
  if (!window.__godmodeRenderOnce) {
    window.__godmodeRenderOnce = function (el, html) {
      if (!el || el.__gmLastHTML === html) return false;
      el.__gmLastHTML = html;
      el.innerHTML = html;
      return true;
    };
  }

  if (window.__godmodeFetchJSON) return;   // api.ts already installed the richer implementation

  var inflight = new Map();
  var cache = new Map();

  function headers() {
    var h = { Accept: 'application/json' };
    try {
      var k = sessionStorage.getItem('godmode_api_key');
      if (k) h['X-GodMode-Key'] = k;
    } catch (e) { /* storage blocked; an unkeyed server does not need the header anyway */ }
    return h;
  }

  window.__godmodeFetchJSON = function (path, ttlMs) {
    var ttl = typeof ttlMs === 'number' ? ttlMs : 700;
    var hit = cache.get(path);
    if (hit && Date.now() - hit.at < ttl) return Promise.resolve(hit.json);

    var pending = inflight.get(path);
    if (pending) return pending;

    var run = fetch(path, { headers: headers(), cache: 'no-store', credentials: 'omit' })
      .then(function (r) { return r.json(); })
      .then(function (json) { cache.set(path, { at: Date.now(), json: json }); return json; })
      .finally(function () { inflight.delete(path); });

    inflight.set(path, run);
    return run;
  };

})();
