from pathlib import Path

from dist_assets import dist_index_html, runtime_script, runtime_style

ROOT = Path(__file__).resolve().parents[2]
BUILD = "V15.4.3-READINESS-COMPONENT-KERNEL"


def test_packaged_dashboard_loads_early_impulse_ui_assets():
    # Matched by stem rather than by exact filename: the script ships with a version suffix
    # (early-impulse-settings-v1529.js) that moves every release, and pinning it here made an
    # unrelated test fail on every revision of the script.
    html = dist_index_html()
    script = runtime_script("early-impulse-settings")
    style = runtime_style("early-impulse-settings")
    assert f'/{style.name}' in html
    assert f'/{script.name}' in html
    assert BUILD in html
    assert script.is_file()
    assert style.is_file()


def test_ui_exposes_every_runtime_early_impulse_setting():
    script = runtime_script("early-impulse-settings").read_text(encoding="utf-8")
    keys = {
        "earlyImpulsePredictorEnabled", "earlyImpulseLiveCandleAnalysis",
        "earlyImpulseDynamicThresholds", "earlyImpulseProgressiveExecution",
        "earlyImpulseWindowSeconds", "earlyImpulseMinTicks",
        "earlyImpulseVelocityAtrPerSecond", "earlyImpulseAccelerationAtrPerSecond",
        "earlyImpulseCompressionRatio", "earlyImpulseBodyAtr",
        "earlyImpulseSpreadExpansionMultiple", "earlyImpulseProbeProbability",
        "earlyImpulseConfirmProbability", "earlyImpulseMinProbeAtr",
        "earlyImpulseMinConfirmAtr", "earlyImpulseMaxExtensionAtr",
        "earlyImpulseMaxSweepPenalty", "earlyImpulseProbeLotMultiplier",
        "earlyImpulseStopAtr", "fastSniperLoopSeconds",
    }
    assert not [key for key in keys if key not in script]
    assert "/api/fast-sniper/status" in script
    assert "/api/settings" in script
    assert "expectedRevision" in script


def test_release_identity_is_exact_across_runtime_surfaces():
    surfaces = [
        ROOT / "backend" / "app.py",
        ROOT / "backend" / "services" / "v15" / "orchestrator.py",
        ROOT / "frontend" / "src" / "lib" / "api.ts",
        ROOT / "frontend" / "dist" / "index.html",
        ROOT / "frontend" / "public" / "v15-enterprise.js",
        ROOT / "mt5_ea" / "GodModeTickGuard.mq5",
        ROOT / "RELEASE_MANIFEST.json",
        ROOT / "START_GODMODE.bat",
    ]
    for path in surfaces:
        assert BUILD in path.read_text(encoding="utf-8"), path
