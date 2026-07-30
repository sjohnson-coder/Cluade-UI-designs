from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
SETTINGS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "Settings.tsx"

def test_dynamic_sl_has_separate_activation_from_legacy_controls():
    src = APP.read_text(encoding="utf-8")
    assert "dynamic_activation if ai_dynamic_stop else legacy_activation" in src
    assert "if not ai_dynamic_stop and (profit_r >= be_at_rr or be_points_hit)" in src

def test_dynamic_tightening_uses_symbol_normalisation():
    src = APP.read_text(encoding="utf-8")
    anchor = "aiDynamicLowScoreTighten"
    idx = src.rindex(anchor)
    part = src[idx:idx+1800]
    assert "_normalize_price(" in part
    assert "round(max(target_sl" not in part

def test_settings_page_removes_legacy_be_trailing_card_and_duplicate_dry_run():
    src = SETTINGS.read_text(encoding="utf-8")
    assert "5b². Break-Even & Trailing" not in src
    assert '<Row label="Dry Run">' not in src
    assert src.count("Reversal scouts (counter-trend)") == 0
