from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_requirements_pin_numpy_1x_before_mt5():
    text = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert 'numpy==1.26.4; platform_system == "Windows"' in text
    assert 'MetaTrader5==5.0.45; platform_system == "Windows"' in text
    assert text.index("numpy==1.26.4") < text.index("MetaTrader5==5.0.45")


def test_launcher_checks_and_repairs_mt5_runtime():
    text = (ROOT / "START_GODMODE.bat").read_text(encoding="utf-8")
    assert "VERIFY_MT5_RUNTIME.py" in text
    assert 'numpy==1.26.4' in text
    assert 'MetaTrader5==5.0.45' in text
    assert "pip uninstall -y numpy MetaTrader5" in text


def test_manual_runtime_repair_is_packaged():
    text = (ROOT / "FIX_MT5_RUNTIME.bat").read_text(encoding="utf-8")
    assert "--force-reinstall" in text
    assert "VERIFY_MT5_RUNTIME.py" in text


def test_runtime_build_ids_match():
    app = (ROOT / "backend" / "app.py").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    ea = (ROOT / "mt5_ea" / "GodModeTickGuard.mq5").read_text(encoding="utf-8")
    expected = "V15.4.3-READINESS-COMPONENT-KERNEL"
    assert f'BUILD_ID = "{expected}"' in app
    assert f"FRONTEND_BUILD_ID='{expected}'" in api
    assert f'ExpectedEngineBuild  = "{expected}"' in ea


def test_cached_settings_bundle_name_was_busted():
    index = (ROOT / "frontend" / "dist" / "index.html").read_text(encoding="utf-8")
    assets = ROOT / "frontend" / "dist" / "assets"
    main_path = next(assets.glob("index-*.js"))
    settings_path = next(assets.glob("Settings-*.js"))
    main = main_path.read_text(encoding="utf-8")
    assert main_path.name in index
    assert settings_path.name in main
    assert settings_path.exists()
