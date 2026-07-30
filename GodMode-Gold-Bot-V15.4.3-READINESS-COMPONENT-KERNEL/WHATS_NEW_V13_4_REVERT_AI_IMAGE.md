# GodMode Gold Bot V13.4 — Reverted the AI image, as you asked

## You were right, and I took your suggestion
What I built was a wireframe outline with dots. Your reference is a photorealistic 3D-rendered
brain with volumetric shading, real depth and lighting. Those are not the same thing, and no
amount of tuning bezier curves on a 2D canvas was going to close that gap. Hand-drawing
anatomical realism in code is not something I can do to that standard, so rather than keep
burning your versions on it, I have done what you suggested and reverted.

## What changed
  • Dashboard restored to the ORIGINAL static AI image (src/assets/godmode-ai-node.svg — it was
    never deleted, so this is a true revert, not a re-creation).
  • NeuralBrain.tsx deleted. Zero references remain anywhere in src/.
  • Verified: braces balanced, no duplicate declarations, aiNode imported and used.

## Everything else from V13.x is INTACT — only the brain is gone
  • Economic Calendar UI: still mounted
  • TradingView-grade chart with realtime series.update() tick: intact
  • Markers only while a trade is live: intact
  • liveTrade gating + live P&L badge: intact
  • One-click start_all.bat (builds UI before opening browser): intact
  • V12.99.x fixes (apply whitelist, history cap 2000, feeds latency, chart truth): intact

## If you want a realistic brain later
The honest options, none of which are me hand-coding anatomy:
  1. A real rendered asset — a stock/AI-generated brain image (like your reference), dropped in
     as a PNG/WebP, with a CSS glow-pulse and an overlaid canvas layer for the electric hot spots
     and the candle waveform. This gets you the reference's realism because the realism comes from
     the asset, not from my geometry.
  2. A 3D model via three.js (r128 is already available in this stack) with a real brain mesh.
     Heavier, and it still needs a proper mesh file.
Option 1 is what I would recommend: you keep the photoreal look you actually want, and the motion
layer is the part code is genuinely good at. Say the word and send/choose an image.

## Validation
Boot fast, endpoints failing: NONE, full regression green. No defaults changed.
