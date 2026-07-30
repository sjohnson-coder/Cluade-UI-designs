from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = "V15.4.3-READINESS-COMPONENT-KERNEL"


def test_packaged_dashboard_loads_early_impulse_ui_assets():
    html = (ROOT / "frontend" / "dist" / "index.html").read_text(encoding="utf-8")
    assert '/early-impulse-settings.css' in html
    assert '/early-impulse-settings.js' in html
    assert BUILD in html
    assert (ROOT / "frontend" / "dist" / "early-impulse-settings.js").is_file()
    assert (ROOT / "frontend" / "dist" / "early-impulse-settings.css").is_file()


def test_ui_exposes_every_runtime_early_impulse_setting():
    script = (ROOT / "frontend" / "dist" / "early-impulse-settings.js").read_text(encoding="utf-8")
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
        ROOT / "frontend" / "dist" / "v15-enterprise.js",
        ROOT / "mt5_ea" / "GodModeTickGuard.mq5",
        ROOT / "RELEASE_MANIFEST.json",
        ROOT / "START_GODMODE.bat",
    ]
    for path in surfaces:
        assert BUILD in path.read_text(encoding="utf-8"), path
