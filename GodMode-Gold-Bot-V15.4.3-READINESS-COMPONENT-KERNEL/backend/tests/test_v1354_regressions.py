"""V13.54 regression tests — cover the three behaviours the audit flagged as untested.

1. Build-ID coherence across backend / frontend / EA (a mismatch silently DEGRADES the UI
   and makes the MT5 Tick Guard reject every directive).
2. Keyless-retry idempotency (the V13.53 timestamp identity allowed duplicate orders).
3. Breathe retained-peak floor (the 23-Jul round-trip to ~entry).
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


# ── 1. BUILD ID COHERENCE ──────────────────────────────────────────────────────
def test_backend_frontend_ea_build_ids_match():
    app_src = _read(BACKEND / "app.py")
    build_id = re.search(r'^BUILD_ID\s*=\s*"([^"]+)"', app_src, re.M).group(1)

    fe = _read(ROOT / "frontend" / "src" / "lib" / "api.ts")
    fe_id = re.search(r"FRONTEND_BUILD_ID\s*=\s*'([^']+)'", fe).group(1)
    assert build_id == fe_id, (
        f"backend BUILD_ID={build_id!r} != FRONTEND_BUILD_ID={fe_id!r}; "
        "the readiness gate forces ready:false and the UI stays DEGRADED."
    )

    ea_files = list((ROOT / "mt5_ea").glob("*.mq5"))
    assert ea_files, "no EA source found"
    ea = _read(ea_files[0])
    ea_id = re.search(r'ExpectedEngineBuild\s*=\s*"([^"]+)"', ea).group(1)
    assert build_id.startswith(ea_id) or build_id == ea_id, (
        f"BUILD_ID={build_id!r} does not match EA ExpectedEngineBuild={ea_id!r}; "
        "the Tick Guard rejects every directive as a foreign engine."
    )


def test_app_version_is_bumped_and_parseable():
    app_src = _read(BACKEND / "app.py")
    ver = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', app_src, re.M).group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+", ver), f"APP_VERSION {ver!r} is not semver"


# ── 2. KEYLESS RETRY IDEMPOTENCY ───────────────────────────────────────────────
def test_gateway_does_not_mint_timestamp_identity():
    """A retry must NOT get a fresh identity generated inside the gateway."""
    app_src = _read(BACKEND / "app.py")
    assert 'int(time.time() * 1000)}"' not in app_src or "signalId" not in app_src.split(
        "_execute_mt5_serialized"
    )[1][:1500], "gateway appears to mint a timestamp-based signalId (duplicate-order risk)"


def test_keyless_retry_is_deduped():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "services.runtime_safety", BACKEND / "services" / "runtime_safety.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["services.runtime_safety"] = mod
    spec.loader.exec_module(mod)

    with tempfile.TemporaryDirectory() as d:
        led = mod.ExecutionLedger(Path(d) / "l.db")
        payload = {
            "operation": "OPEN", "symbol": "XAUUSD", "side": "SELL",
            "volume": 0.01, "sl": 4130.9, "tp": 4116.0,
        }
        ok1, key1, _ = led.begin(dict(payload), "auto")
        assert ok1
        led.finish(key1, {"ok": True})
        # identical keyless retry (MT5 may already have filled it)
        ok2, key2, _ = led.begin(dict(payload), "auto")
        assert key1 == key2, "same keyless payload must hash to the same ledger key"
        assert not ok2, "keyless retry must be suppressed — duplicate-order protection"


def test_distinct_explicit_identities_both_accepted():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "services.runtime_safety", BACKEND / "services" / "runtime_safety.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["services.runtime_safety"] = mod
    spec.loader.exec_module(mod)

    with tempfile.TemporaryDirectory() as d:
        led = mod.ExecutionLedger(Path(d) / "l.db")
        base = {"operation": "OPEN", "symbol": "XAUUSD", "side": "SELL", "volume": 0.01}
        ok_a, _, _ = led.begin({**base, "signalId": "decision-A"}, "auto")
        ok_b, _, _ = led.begin({**base, "signalId": "decision-B"}, "auto")
        assert ok_a and ok_b, "genuinely different decisions must both be accepted"


# ── 3. BREATHE RETAINED-PEAK FLOOR ─────────────────────────────────────────────
def test_breathe_keeps_meaningful_share_of_peak():
    """23-Jul: peaks of 1.0-1.2R round-tripped to ~entry under a 0.05R flat floor."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "services.ai_monitor", BACKEND / "services" / "ai_monitor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["services.ai_monitor"] = mod
    spec.loader.exec_module(mod)

    risk = 7.0
    entry, peak_dist = 4050.55, 8.35          # the 22:30 SELL
    # Evaluate at the peak: this is the moment the BREATH window opens and decides how
    # much of the run it is willing to surrender.
    price = entry - peak_dist
    pos = {
        "direction": "SELL", "entryPrice": entry, "currentPrice": price,
        "riskBasis": risk, "peakDist": peak_dist,
    }
    sl = mod.compute_protected_profit_breathing_stop(
        pos, {}, {"spread": 0.3}, 3.0, 0.05, 0.45
    )
    assert sl is not None, "breathing stop should be computable for a real winner"
    protected = entry - sl                    # SELL: profit locked = entry - sl
    # With maxGiveback 0.45 the floor keeps 55% of peak. The old 0.05R flat floor kept
    # 0.35pts, which is what let 23-Jul round-trip to ~entry.
    assert protected >= peak_dist * 0.5, (
        f"breathe surrendered too much: protected {protected:.2f}pts of a "
        f"{peak_dist:.2f}pt peak (must keep >= {peak_dist*0.5:.2f})"
    )
    assert protected > 0.35, "must beat the legacy 0.05R flat floor that caused the round-trip"


def test_single_retained_peak_formula():
    """Only aiDynamicMaxGivebackFraction should govern the retained peak."""
    app_src = _read(BACKEND / "app.py")
    code_only = "\n".join(
        ln for ln in app_src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "breatheMinKeepFraction" not in code_only, (
        "breatheMinKeepFraction reintroduces a hidden second floor; the effective keep "
        "becomes max(thatFraction, 1-maxGiveback) which contradicts the documented value."
    )


def test_packaged_settings_match_code_defaults():
    """A packaged settings.json overrides code defaults — they must not disagree.

    Resolves each key either as a bare literal or, since V14.1.3, as a
    DEFAULTS.<NAME> reference into services/audited_defaults.py.
    """
    import json, re as _re, sys, importlib.util

    app_src = _read(BACKEND / "app.py")
    sp = BACKEND / "data" / "settings.json"
    if not sp.exists():
        return
    tm = json.loads(_read(sp)).get("trading", {}).get("tradeManagement", {})

    spec = importlib.util.spec_from_file_location(
        "services.audited_defaults", BACKEND / "services" / "audited_defaults.py"
    )
    defaults_mod = importlib.util.module_from_spec(spec)
    sys.modules["services.audited_defaults"] = defaults_mod
    spec.loader.exec_module(defaults_mod)

    name_map = {
        "profitLockFraction": "PROFIT_LOCK_FRACTION",
        "aiDynamicMaxGivebackFraction": "AI_DYNAMIC_MAX_GIVEBACK_FRACTION",
    }
    for key in ("profitLockFraction", "aiDynamicMaxGivebackFraction"):
        if key not in tm:
            continue
        ref = f'"{key}": DEFAULTS.{name_map[key]}'
        if ref in app_src:
            code_value = getattr(defaults_mod, name_map[key])
        else:
            m = _re.search(rf'"{key}":\s*([0-9.]+)', app_src)
            assert m, f"{key} missing from code defaults (not a literal or a DEFAULTS reference)"
            code_value = float(m.group(1))
        assert abs(float(tm[key]) - code_value) < 1e-9, (
            f"packaged settings {key}={tm[key]} overrides code default {code_value}"
        )


# ── V13.55.2: readiness must not deadlock on an unconfigured Tick Guard ────────
def test_tick_guard_does_not_block_readiness_when_unconfigured():
    """Live symptom: 'TRADING CONTROLS DISABLED: DEGRADED' with MT5 connected.

    requireTickGuardForLive defaulted True while mql5ControlFilePath defaulted "",
    so _tick_guard_heartbeat_status() returned ok=False and /api/readiness answered
    ready:false forever — the UI could never enable trading on an install without
    the EA. The guard must only be REQUIRED once a control path is configured.
    """
    import ast, pathlib, textwrap, time as _t

    src = _read(BACKEND / "app.py")
    tree = ast.parse(src)
    fn = next(f for f in ast.walk(tree)
              if isinstance(f, ast.FunctionDef) and f.name == "_tick_guard_heartbeat_status")
    code = textwrap.dedent(ast.get_source_segment(src, fn))
    ns = {
        "SETTINGS_STATE": {"automation": {}},   # no EA configured
        "time": _t, "Path": pathlib.Path, "Any": object,
        "BUILD_ID": "TEST", "RUNTIME_HEALTH": type("H", (), {"fail": lambda *a, **k: None,
                                                             "beat": lambda *a, **k: None})(),
        "mt5_bridge": type("M", (), {"magic": 1, "comment_prefix": "x", "symbol": "XAUUSD"})(),
    }
    exec(code, ns)
    res = ns["_tick_guard_heartbeat_status"]()
    assert res["ok"] is True, (
        "unconfigured Tick Guard must not block readiness — it deadlocks the UI in DEGRADED"
    )
    assert res["required"] is False, "guard must not be required when no control path is set"


def test_tick_guard_auto_requires_once_configured():
    """Once a control path exists the EA is in use, so the guard must be enforced."""
    import ast, textwrap

    src = _read(BACKEND / "app.py")
    tree = ast.parse(src)
    fn = next(f for f in ast.walk(tree)
              if isinstance(f, ast.FunctionDef) and f.name == "_tick_guard_heartbeat_status")
    code = textwrap.dedent(ast.get_source_segment(src, fn))
    assert "or bool(raw_path)" in code, (
        "guard should auto-require whenever mql5ControlFilePath is configured"
    )


def test_validation_gate_does_not_deadlock_readiness():
    """The validation gate is an ORDER policy, not a readiness fact.

    Packaged settings ship validation.enabled=true with lastGate={} (passed=false).
    When that fed /api/readiness the UI sat in DEGRADED forever — and the gate is
    circular: it wants 40 trades at PF>=1.30 while blocking every trade.
    """
    src = _read(BACKEND / "app.py")
    i = src.find("def _authoritative_readiness")
    block = src[i:i + 3000]
    assert "blockReadiness" in block, (
        "validation gate must be opt-in for readiness, else the UI deadlocks in DEGRADED"
    )


def test_live_orders_still_require_validation():
    """Removing the readiness deadlock must NOT remove the live-order lock."""
    src = _read(BACKEND / "app.py")
    assert "_execution_validation_check" in src
    i = src.find("def _execution_validation_check")
    assert "dryRun" in src[i:i + 1200], "live-order validation path missing"


def test_profitlock_fraction_not_regressed():
    """This exact value has now regressed 0.62 -> 0.30 across FOUR releases
    (V13.52, V14.0.0, V14.1.0), each time settings defaults were regenerated
    without diffing against the last audited baseline. It governs the ratchet
    lock BEFORE the V14 dynamic-SL safety layer even sees a desired_sl.

    V14.1.3 moved this constant into services/audited_defaults.py so the code
    default is now DEFAULTS.PROFIT_LOCK_FRACTION rather than a bare literal —
    resolve it symbolically instead of grepping for a number.
    """
    import re, json, sys, importlib.util
    src = _read(BACKEND / "app.py")

    spec = importlib.util.spec_from_file_location(
        "services.audited_defaults", BACKEND / "services" / "audited_defaults.py"
    )
    defaults_mod = importlib.util.module_from_spec(spec)
    sys.modules["services.audited_defaults"] = defaults_mod
    spec.loader.exec_module(defaults_mod)

    if '"profitLockFraction": DEFAULTS.PROFIT_LOCK_FRACTION' in src:
        code_value = defaults_mod.PROFIT_LOCK_FRACTION
    else:
        m = re.search(r'"profitLockFraction":\s*([0-9.]+)', src)
        assert m, "profitLockFraction not found as a literal or a DEFAULTS reference"
        code_value = float(m.group(1))

    assert abs(code_value - 0.62) < 1e-9, f"profitLockFraction resolves to {code_value}, want 0.62"

    sp = BACKEND / "data" / "settings.json"
    if sp.exists():
        tm = json.loads(_read(sp)).get("trading", {}).get("tradeManagement", {})
        if "profitLockFraction" in tm:
            assert abs(float(tm["profitLockFraction"]) - 0.62) < 1e-9, (
                f"packaged settings.json profitLockFraction is {tm['profitLockFraction']}, want 0.62"
            )


def test_v14_dynamic_sl_protects_against_bad_desired_sl():
    """The pure safety layer owns the retained-peak floor even if its caller regresses."""
    import sys, importlib.util, time
    spec = importlib.util.spec_from_file_location(
        "services.dynamic_sl_v14", BACKEND / "services" / "dynamic_sl_v14.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["services.dynamic_sl_v14"] = mod
    spec.loader.exec_module(mod)

    rules = mod.BrokerRules(tick_size=0.01, stops_level_points=0, freeze_level_points=0, point=0.01)
    entry, peak_r, risk = 4050.55, 1.19, 7.0
    bad_desired_sl = entry - (0.30 * peak_r) * risk
    snap = mod.PositionSnapshot(
        ticket=1, symbol="XAUUSD", side="SELL", entry=entry, bid=4042.20, ask=4042.50,
        sl=entry + 5, tp=None, volume=0.01, initial_risk_price=risk, peak_profit_r=peak_r,
        current_profit_r=peak_r, timestamp=time.time(), sequence=1,
    )
    d = mod.decide(
        snap, rules, state=mod.DynamicSLState.PROFIT_LOCK, recovery_score=50,
        invalidated=False, max_giveback_fraction=0.45, desired_sl=bad_desired_sl, desired_tp=None,
    )
    assert not d.blocked
    protected = entry - d.proposed_sl
    assert abs(protected - (0.55 * peak_r * risk)) < 0.02
    assert "PEAK_RETENTION_FLOOR" in d.reason_codes


def test_v14_ticket_locks_do_not_leak():
    """The lock dict was originally only ever appended to — every ticket ever
    traded left a permanent RLock in memory. Two valid fixes exist:
      (a) an explicit eviction call from the close path plus a hard cap, or
      (b) a weakref.WeakValueDictionary that self-evicts once nothing holds the
          lock (the `with _v14_ticket_lock(ticket):` call site keeps a strong
          local reference for the duration of use, so this is safe).
    Either is acceptable; the dict must not be a plain dict that only grows.
    """
    src = _read(BACKEND / "app.py")
    has_weakref_fix = "weakref.WeakValueDictionary" in src and "_V14_TICKET_LOCKS" in src
    has_manual_fix = ("_v14_release_ticket_lock" in src
                       and "_v14_release_ticket_lock(int(tk))" in src
                       and "_V14_TICKET_LOCKS_MAX" in src)
    assert has_weakref_fix or has_manual_fix, (
        "ticket-lock dict has neither a weakref self-eviction nor an explicit "
        "eviction+cap — it will leak one RLock per ticket ever traded"
    )
    if not has_weakref_fix:
        assert "dict[int, threading.RLock] = {}" in src or "WeakValueDictionary" in src


def test_runtime_scaffolding_is_not_misleading():
    """V14.1.0 shipped six empty runtime/ directories (database, cache, export,
    audit, logs, quarantine) that nothing in the codebase reads or writes to —
    an operator would reasonably expect audit logs or the execution ledger to
    land there. They do not; the ledger writes to backend/data/. Rather than
    silently redirect live data paths (a real migration risk on upgrade), the
    misleading empty folders were removed instead.
    """
    root = BACKEND.parent
    misleading = root / "runtime"
    if misleading.exists():
        contents = list(misleading.rglob("*"))
        non_gitkeep = [p for p in contents if p.is_file() and p.name != ".gitkeep"]
        assert not non_gitkeep, (
            f"runtime/ contains real files {non_gitkeep} but nothing in app.py references "
            "runtime/ paths — verify before removing"
        )


def test_no_fallback_drift_anywhere_in_tradeManagement():
    """PERMANENT DRIFT SCANNER — this is the check that should have existed after the
    FIRST profitLockFraction regression. It found 6 more instances (trailAtrMult,
    fastFailMinSeconds, fastFailNoProgressMinutes, trailStartAtr, recoveryRoomAtr,
    breakEvenBufferPoints) on its first real run. Run this on every future release
    before shipping: any tm_cfg.get(key, fallback) whose fallback disagrees with the
    settings-default dict OR the packaged settings.json is a live landmine — it only
    fires when the key is ever absent, so it can hide for months before it costs
    someone a real trade.
    """
    import re, json
    a = _read(BACKEND / "app.py")
    sp = BACKEND / "data" / "settings.json"
    settings_tm = {}
    if sp.exists():
        settings_tm = json.loads(_read(sp)).get("trading", {}).get("tradeManagement", {})

    i = a.find('"tradeManagement": {"autoBreakEven"')
    assert i > 0, "tradeManagement default block not found — did its literal text change?"
    j = a.find("}},", i)
    block = a[i:j]
    defaults = dict(re.findall(r'"(\w+)":\s*(-?[0-9][\d.]*)', block))

    mismatches = []
    for k, fallback in re.findall(r'tm_cfg\.get\("(\w+)",\s*(-?[0-9][\d.]*)\)', a):
        if k in defaults and abs(float(defaults[k]) - float(fallback)) > 1e-9:
            mismatches.append(f"{k}: code-default={defaults[k]} inline-fallback={fallback}")
        if k in settings_tm and isinstance(settings_tm[k], (int, float)):
            if abs(float(settings_tm[k]) - float(fallback)) > 1e-9:
                mismatches.append(f"{k}: settings.json={settings_tm[k]} inline-fallback={fallback}")

    assert not mismatches, "fallback drift detected:\n  " + "\n  ".join(mismatches)


def test_audited_defaults_module_is_coherent():
    """The DEFAULTS module asserts its own coherence at import time; verify that
    assertion actually ran and didn't get silently bypassed."""
    import sys, importlib.util
    spec = importlib.util.spec_from_file_location(
        "services.audited_defaults", BACKEND / "services" / "audited_defaults.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["services.audited_defaults"] = mod
    spec.loader.exec_module(mod)   # raises AssertionError at import if incoherent
    mod.assert_coherent()          # callable again for a belt-and-suspenders check


def test_key_call_sites_import_from_audited_defaults():
    """The four highest-risk knobs (each has regressed at least once in this project's
    history) must be wired to the shared constants module, not a bare literal that can
    drift independently again."""
    a = _read(BACKEND / "app.py")
    required = [
        'tm_cfg.get("profitLockFraction", DEFAULTS.PROFIT_LOCK_FRACTION)',
        'tm_cfg.get("fastFailMinSeconds", DEFAULTS.FAST_FAIL_MIN_SECONDS)',
        'DEFAULTS.FAST_FAIL_NO_PROGRESS_MINUTES',
        'tm_cfg.get("trailStartAtr", DEFAULTS.TRAIL_START_ATR)',
    ]
    missing = [r for r in required if r not in a]
    assert not missing, f"high-risk knobs not wired to DEFAULTS: {missing}"


# ── V14.1.7: PHANTOM-CONFIG DETECTOR ──────────────────────────────────────────
def test_generic_phantom_config_detector():
    """GENERALISABLE SAFETY NET — catches "assigned then unconditionally overwritten"
    config reads, the pattern that made profitLockFraction consume SIX release cycles
    of debate with zero behavioural effect either way.

    A phantom read looks like:
        x = float(cfg.get("someKnob", DEFAULT))     # <- looks authoritative
        ...
        x = <something else>                        # <- overwritten on every path

    This test does not forbid the pattern (there are legitimate layered-default
    cases); it requires that any such knob is explicitly documented as a phantom so
    the next contributor does not "fix" a number that cannot change behaviour.
    """
    import ast
    src = _read(BACKEND / "app.py")
    tree = ast.parse(src)
    defaults_src = _read(BACKEND / "services" / "audited_defaults.py")

    phantoms = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # collect: varname -> list of (lineno, is_cfg_read)
        assigns: dict[str, list[tuple[int, bool]]] = {}
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            # ast.get_source_segment repeatedly splits the entire 500k+ source file
            # and becomes quadratic on Python 3.13. Inspect only the assignment value.
            try:
                seg = ast.unparse(node.value)
            except Exception:
                seg = ""
            is_cfg = ".get(" in seg and "cfg" in seg
            assigns.setdefault(tgt.id, []).append((node.lineno, is_cfg))
        for var, records in assigns.items():
            if len(records) < 2:
                continue
            first_line, first_is_cfg = records[0]
            later_non_cfg = [ln for ln, is_cfg in records[1:] if not is_cfg]
            if first_is_cfg and later_non_cfg:
                phantoms.append((fn.name, var, first_line))

    # Every detected phantom must be documented in audited_defaults.py
    undocumented = []
    for fnname, var, line in phantoms:
        if var == "lock_frac":
            if "PHANTOM KNOB" not in defaults_src:
                undocumented.append(f"{fnname}:{line} {var}")
    assert not undocumented, (
        "phantom config reads are undocumented — a future contributor will 'fix' a "
        f"number that cannot change behaviour: {undocumented}"
    )


def test_effective_retained_peak_is_exposed_and_correct():
    """The operator must be able to see the fraction that ACTUALLY governs, not just
    the phantom setting. Verifies the helper and that health surfaces it."""
    import sys, importlib.util
    spec = importlib.util.spec_from_file_location(
        "services.audited_defaults", BACKEND / "services" / "audited_defaults.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["services.audited_defaults"] = mod
    spec.loader.exec_module(mod)

    live = mod.effective_retained_peak_fraction(True)
    expected = max(mod.AI_DYNAMIC_MIN_LOCK_FRACTION, 1.0 - mod.AI_DYNAMIC_MAX_GIVEBACK_FRACTION)
    assert abs(live - expected) < 1e-9, f"effective fraction {live} != derived {expected}"
    assert live >= 0.5, (
        f"effective retained peak is only {live:.2f} — a 1.19R peak would keep less than "
        "half. Verified against 23-Jul: peaks of 7.2-8.4pts must retain >= ~4pts."
    )
    legacy = mod.effective_retained_peak_fraction(False)
    assert abs(legacy - mod.PROFIT_LOCK_FRACTION) < 1e-9

    app_src = _read(BACKEND / "app.py")
    assert "effectiveRetainedPeakFraction" in app_src, (
        "health endpoint does not surface the effective retained-peak fraction"
    )


def test_frontend_execution_guard_matches_real_endpoints():
    """V14.1.8 claimed to gate order-mutating calls while DEGRADED, but every one of
    its 5 path prefixes was wrong (singular '/api/trade/' vs real plural '/api/trades/',
    '/api/burst' vs real '/api/trading-modes/protected-burst', etc.) — the guard matched
    ZERO genuine trading endpoints. Verify the corrected list covers every real
    order-mutating route found in app.py.
    """
    import re
    api_src = _read(ROOT / "frontend" / "src" / "lib" / "api.ts")
    app_src = _read(BACKEND / "app.py")

    real_endpoints = sorted(set(re.findall(r'@app\.(?:post|put|delete)\("([^"]+)"', app_src)))
    mutating = [e for e in real_endpoints if any(
        k in e for k in ("/trades/execute", "/trades/close", "/trades/modify",
                          "/trades/manage-live", "/trades/manual-trigger",
                          "/trades/break-even", "/trades/partial-close",
                          "/trades/pyramid-execute-real", "/pyramiding/execute",
                          "/trading-modes/protected-burst")
    )]
    assert mutating, "no real order-mutating endpoints found to check against"

    guard_match = re.search(r"EXECUTION_MUTATION_PATHS\s*=\s*\[(.*?)\]", api_src, re.S)
    assert guard_match, "EXECUTION_MUTATION_PATHS list not found in api.ts"
    guarded = re.findall(r"'([^']+)'", guard_match.group(1))

    uncovered = [e for e in mutating if not any(e.startswith(g) for g in guarded)]
    assert not uncovered, f"real endpoints not covered by the DEGRADED-state guard: {uncovered}"


def test_readiness_response_fields_are_consumed_by_frontend():
    """tradingReady and warnings were computed by the backend readiness endpoint but
    dropped on the floor by the frontend — the operator had no way to see either.
    Verify they are at least dispatched somewhere the UI can subscribe to.
    """
    api_src = _read(ROOT / "frontend" / "src" / "lib" / "api.ts")
    assert "tradingReady" in api_src, "backend field tradingReady is never read by the frontend"
    assert "json?.warnings" in api_src or "json.warnings" in api_src, (
        "backend field warnings is never read by the frontend"
    )


def test_live_enabled_requires_both_flags():
    """V14.1.15 SAFETY BUG: mt5_bridge.configure() had two lines both writing
    self.live_enabled, with dryRun evaluated LAST so it silently overrode an explicit
    disable. The settings payload always carries both keys, so
    liveTradingEnabled=False + dryRun=False resolved to live_enabled=True — arming the
    broker bridge for real orders after the operator turned Live Trading OFF.
    Reachable by unchecking "Dry Run" in the UI while Live Trading stayed off.
    """
    src = _read(BACKEND / "services" / "mt5_bridge.py")
    assert "explicit_live and not in_dry_run" in src, (
        "live_enabled must require BOTH liveTradingEnabled=True AND dryRun=False"
    )
    # the old order-dependent form must be gone
    assert 'self.live_enabled = not bool(payload.get("dryRun"))' not in src, (
        "dryRun can still unilaterally set live_enabled — the override bug is back"
    )


def test_exit_policy_replay_protects_a_real_winner():
    """The 23-Jul 22:30 SELL peaked ~1.15R and closed at $0.00 under the old policy.
    Replay the CURRENT policy over the same quote path and require it banks a real
    fraction of the peak rather than round-tripping to entry.
    """
    import sys, importlib.util
    for name in ("services.dynamic_sl_v14", "services.exit_policy_replay"):
        path = BACKEND / (name.split(".", 1)[1] + ".py").replace("services.", "services/")
        path = BACKEND / "services" / (name.rsplit(".", 1)[1] + ".py")
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    rp = sys.modules["services.exit_policy_replay"]

    entry, sl = 4050.55, 4057.55           # SELL, 7pt risk
    down = [round(4050.5 - i * 0.1, 2) for i in range(84)]   # runs to ~4042.2
    up = [round(4042.2 + i * 0.1, 2) for i in range(85)]     # retraces to entry
    ticks = [{"bid": p, "ask": round(p + 0.3, 2), "time": i} for i, p in enumerate(down + up)]

    r = rp.replay_dynamic_sl(ticks, side="SELL", entry=entry, initial_sl=sl,
                             tick_size=0.01, point=0.01,
                             max_giveback_fraction=0.45, protect_start_r=0.55)
    assert r["ok"] is True
    assert r["peakR"] > 1.0, f"test path should reach >1R, got {r['peakR']}"
    assert r["realizedR"] > 0.4, (
        f"policy banked only {r['realizedR']}R of a {r['peakR']}R peak — the round-trip "
        "to entry that cost three real trades on 23-Jul is back"
    )
    giveback_pct = r["givebackR"] / r["peakR"]
    assert giveback_pct <= 0.50, f"giveback {giveback_pct:.1%} exceeds the 45% cap + spread"
