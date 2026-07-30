# V15.0.7 Deterministic Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task.

**Goal:** Deliver V15.0.7 with deterministic protection ownership and tick-accurate missed-move replay.

**Architecture:** Add pure timing/ATR/replay helpers, extend the MT5 bridge, integrate them into the management loop, make Tick Guard the exclusive automated stop actuator under fresh directives, then update identity and verify the release.

**Tech Stack:** Python, FastAPI, pytest, MetaTrader5 API, MQL5, packaged React/Vite.

## Global Constraints
- Base: V15.0.6.
- Target: V15.0.7-DETERMINISTIC-PROTECTION-HARDENED.
- Preserve CSS/UI styling and entry strategy.
- Do not weaken safety gates.

### Tasks
- [x] Add pure protection determinism helpers and tests.
- [x] Add MT5 open/tick millisecond timestamps and tick-range replay.
- [x] Replace missed-move candle hindsight with executable bid/ask replay and event dedupe.
- [x] Replace management check counters with elapsed seconds and broker-derived age.
- [x] Gate breathing/V14 on broker confirmation, threshold and valid ATR.
- [x] Persist peaks and broker-confirmed SL changes immediately.
- [x] Add exclusive PROTECT/BREATH/RECOVER/HOLD/CUT Tick Guard directives.
- [x] Update release identity, manifests and verification.
