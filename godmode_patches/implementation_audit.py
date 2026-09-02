import json, re, subprocess, os
B="build"
app=open(f"{B}/backend/app.py",encoding="utf-8").read()
S=json.load(open(f"{B}/GODMODE_SETTINGS_V15_10_4_R68_19_EXECUTION_ECONOMICS.json"))
def g(path,d=None):
    cur=S
    for p in path.split("."):
        if not isinstance(cur,dict): return d
        cur=cur.get(p)
    return cur if cur is not None else d
def has(pat, path=None):
    src=app if path is None else open(f"{B}/{path}",encoding="utf-8").read() if os.path.exists(f"{B}/{path}") else ""
    return bool(re.search(pat,src))
def svc(name): return os.path.exists(f"{B}/backend/services/{name}")

CHECKS=[
 # (id, area, requirement, implemented?, evidence)
 ("R1","Telegram","Policy blocks separated from execution failures",
   has(r"classify_execution_outcome|policy_block"), "no classifier in app.py"),
 ("R2","Telegram","'order not filled' routed to throttled rejection class",
   bool(re.search(r'"order not filled" in tl', app)), "rejection class misses the phrase"),
 ("R3","Telegram","Block latch: alert on state transition not per attempt",
   has(r"BlockLatch|block_latch"), "every blocked dispatch alerts"),
 ("R4","Telegram","Pre-dispatch news gate on the direct path",
   has(r"gate a known blackout BEFORE the dispatch"), "guard runs inside dispatch"),
 ("R5","Telegram","Dedupe window configured", g("telegram.dedupeSeconds") is not None,
   f"dedupeSeconds={g('telegram.dedupeSeconds')}"),
 ("R6","Telegram","Management/burst blocker throttles", g("tradingModes.protectedBurst.blockerNoticeSeconds") is not None,
   f"blockerNoticeSeconds={g('tradingModes.protectedBurst.blockerNoticeSeconds')}"),

 ("C1","Cost","Cost-relative minimum stop (stop >= K x round-trip cost)",
   has(r"minStopCostMultiple|cost_relative_stop"), "absent"),
 ("C2","Cost","Fixed point stop floor superseded by the cost gate",
   g("automation.costRelativeStopEnabled") is True and float(g("automation.minStopCostMultiple") or 0)*0.44 > float(g("automation.earlyIntentProbeMinStopPoints") or 0),
   f"cost gate min ${float(g('automation.minStopCostMultiple') or 0)*0.44:.2f} > fixed floor ${g('automation.earlyIntentProbeMinStopPoints')}"),
 ("C3","Cost","Spread cap as fraction of ATR", g("ai.maxSpreadAtrFrac") is not None,
   f"maxSpreadAtrFrac={g('ai.maxSpreadAtrFrac')}"),
 ("C4","Cost","Absolute spread cap", g("ai.maxSpread") is not None, f"maxSpread={g('ai.maxSpread')}"),
 ("C5","Cost","Slippage modelled in cost", g("brokerCosts.slippage") is not None,
   f"slippage={g('brokerCosts.slippage')} exit={g('brokerCosts.exitSlippage')}"),
 ("C6","Cost","Round-trip cost viability ceiling (research overlay)",
   g("ai.researchClockMaxRoundTripCost") is not None, f"={g('ai.researchClockMaxRoundTripCost')}"),

 ("B1","Burst","Descending lot ladder (largest leg at best price)", None, ""),
 ("B2","Burst","Burst lot caps actually enforced", g("tradingModes.protectedBurst.enforceSeparateLotCap") is True,
   f"enforceSeparateLotCap={g('tradingModes.protectedBurst.enforceSeparateLotCap')}"),
 ("B3","Burst","Per-leg cost gate", has(r"_burst_leg_preflight_lot[\s\S]{0,600}?cost_relative|evaluate_stop"), "leg preflight has no cost gate"),
 ("B4","Burst","ATR-relative burst stop room", g("tradingModes.protectedBurst.minBurstStopDistanceAtr") is not None,
   f"minBurstStopDistanceAtr={g('tradingModes.protectedBurst.minBurstStopDistanceAtr')}"),
 ("B5","Burst","One batch per campaign", g("tradingModes.protectedBurst.oneBatchPerCampaign") is True,
   f"={g('tradingModes.protectedBurst.oneBatchPerCampaign')}"),
 ("B6","Burst","Armed-retest timing guard", has(r"evaluate_burst_timing_guard"), ""),
 ("B7","Burst","Arming gated on realised session range", g("tradingModes.protectedBurst.sessionRangeGateEnabled") is True or __import__("os").path.exists("build/backend/services/burst_session_room.py"), "time/score only"),
 ("B8","Burst","No add to a losing position", g("tradingModes.protectedBurst.baseProofMinR") is not None,
   f"baseProofMinR={g('tradingModes.protectedBurst.baseProofMinR')}"),

 ("S1","Session","Research clock policy present", svc("research_clock_policy.py"), ""),
 ("S2","Session","Overlay defaults to SHADOW", str(g("ai.researchClockPolicyMode")).upper()=="SHADOW",
   f"mode={g('ai.researchClockPolicyMode')}"),
 ("S3","Session","Risk multiplier opt-in only", g("ai.researchClockApplyRiskMultiplier") is False,
   f"={g('ai.researchClockApplyRiskMultiplier')}"),
 ("S4","Session","Reopen artifact avoided (18:05 not 18:00)",
   has(r"18\s*\*\s*60\s*\+\s*5", "backend/services/research_clock_policy.py"), ""),
 ("S5","Session","Friday flat boundary", has(r"friday|FRIDAY", "backend/services/research_clock_policy.py"), ""),
 ("S6","Session","Session weight is sizing-only, never an entry switch", None, ""),
 ("S7","Session","Separate intraday weight (distinct from exposure weight)",
   g("ai.researchClockIntradaySeparateWeights") is True, "exposure weight reused"),

 ("V1","Validation","Walk-forward harness", svc("walk_forward.py"), ""),
 ("V2","Validation","Exact broker replay", svc("exact_broker_replay.py"), ""),
 ("V3","Validation","Decision/trade telemetry store", svc("trade_review_store.py"), ""),
 ("V4","Validation","Probability calibration", has(r"isotonic|platt|calibrat", "backend/services/v15/probability_engine.py"), ""),
 ("V5","Validation","Daily loss circuit breaker", g("risk.maxDailyLossPct") is not None, f"={g('risk.maxDailyLossPct')}%"),
 ("V6","Validation","Post-loss cooldown", g("automation.postLossCooldownEnabled") is True,
   f"={g('automation.postLossCooldownMinutes')} min"),
 ("V7","Validation","No martingale / loss-recovery ladder",
   not has(r"(?<!anti-)martingale_(lot|size|multiplier)|double_after_loss|recover_lot_multiplier"), "only anti-martingale comments present"),
]
# B1 computed
pb=g("tradingModes.protectedBurst") or {}
sl=float(pb.get("startLot") or 0); inc=float(pb.get("lotIncrement") or 0); n=int(pb.get("batchSize") or 0)
legs=[round(sl+inc*i,4) for i in range(n)]
b1_ok = len(legs)>1 and all(legs[i]>=legs[i+1] for i in range(len(legs)-1))
S6_ok = None

out=[]
for cid,area,req,ok,ev in CHECKS:
    if cid=="B1": ok, ev = b1_ok, f"active ladder {legs} = {'ASCENDING' if not b1_ok else 'descending'}"
    if cid=="S6": ok, ev = "manual", "verify at promotion; SHADOW today"
    out.append((cid,area,req,ok,ev))

done=sum(1 for r in out if r[3] is True)
todo=[r for r in out if r[3] is False]
print(f"{'ID':<4} {'AREA':<11} {'STATUS':<8} REQUIREMENT")
print("-"*104)
for cid,area,req,ok,ev in out:
    st = "DONE" if ok is True else ("MANUAL" if ok=="manual" else "MISSING")
    print(f"{cid:<4} {area:<11} {st:<8} {req}")
    if ok is not True and ev: print(f"{'':<24} -> {ev}")
print("-"*104)
print(f"{done}/{len(out)} implemented · {len(todo)} gaps")
json.dump([{"id":c,"area":a,"req":r,"ok":(o if o!='manual' else None),"evidence":e} for c,a,r,o,e in out],
          open("audit.json","w"),indent=1)
