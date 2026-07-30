from pathlib import Path
import backend.app as app

def test_public_settings_show_mask_and_configured_flag():
    s={"telegram":{"botToken":"abc123","chatId":"42"}}
    public=app._safe_public_settings(s)
    assert public["telegram"]["botToken"]==""
    assert public["telegram"]["botTokenConfigured"] is True
    assert public["telegram"]["botTokenConfigured"] is True
    clean=app._drop_blank_secrets({"telegram":{"botToken":"••••••••","chatId":"42"}})
    assert "botToken" not in clean["telegram"]

def test_control_bridge_falls_back_when_replace_denied(monkeypatch,tmp_path):
    monkeypatch.setattr(app,"_tick_guard_base_dir",lambda:(tmp_path,"test",str(tmp_path)))
    def denied(*a,**k): raise PermissionError(5,"denied")
    monkeypatch.setattr(app.os,"replace",denied)
    monkeypatch.setattr(app.time,"sleep",lambda *_:None)
    app._write_mql5_control(["1,HOLD,0,1,2,build,1,3"] )
    assert (tmp_path/"godmode_control.csv").read_text().startswith("1,HOLD")
