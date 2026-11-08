"""Tests for S.A.R.A.T.H.I. Mark VII Tactical HUD Web Bridge."""

import pytest

from core.orchestrator import AssistantOrchestrator
from gui.web_bridge import SarathiWebBridge


@pytest.fixture
def bridge():
    orchestrator = AssistantOrchestrator()
    return SarathiWebBridge(orchestrator)


def test_bridge_telemetry(bridge):
    telem = bridge.get_telemetry()
    assert "cpu_pct" in telem
    assert "cores" in telem
    assert len(telem["cores"]) == 12
    assert "ram_pct" in telem
    assert "ram_used_gb" in telem
    assert "disk_free_gb" in telem
    assert "uptime_hours" in telem
    assert telem["cpu_pct"] >= 0.0


def test_bridge_initial_data(bridge):
    init_data = bridge.get_initial_data()
    assert "settings" in init_data
    assert "audio_devices" in init_data
    assert "telemetry" in init_data
    assert init_data["settings"]["assistant_name"] == "SARATHI"
    assert "inputs" in init_data["audio_devices"]
    assert "outputs" in init_data["audio_devices"]


def test_bridge_quick_action_volume(bridge):
    res = bridge.execute_quick_action("volume_50")
    assert res.get("status") == "ok"


def test_bridge_quick_action_purge(bridge):
    res = bridge.execute_quick_action("purge_cache")
    assert res.get("status") == "ok"


def test_bridge_quick_action_diagnostics(bridge):
    res = bridge.execute_quick_action("diagnostics")
    assert res.get("status") == "ok"


def test_bridge_save_settings_persistence(bridge, tmp_path, monkeypatch):
    test_env = tmp_path / ".env"
    test_env.write_text('DEFAULT_LLM_PROVIDER="groq"\nASSISTANT_NAME="SARATHI"\n', encoding="utf-8")

    from config.settings import settings
    orig_groq = settings.GROQ_API_KEY
    orig_gemini = settings.GEMINI_API_KEY
    orig_el_key = settings.ELEVENLABS_API_KEY
    orig_el_vid = settings.ELEVENLABS_VOICE_ID
    orig_llm = settings.DEFAULT_LLM_PROVIDER
    orig_tts = settings.TTS_PROVIDER

    monkeypatch.setattr("gui.web_bridge.EXE_DIR", tmp_path)
    monkeypatch.setattr("gui.web_bridge.BASE_DIR", tmp_path)

    payload = {
        "groq_key": "gsk_test_mock_12345",
        "gemini_key": "AIza_mock_67890",
        "elevenlabs_key": "xi_mock_abcdef",
        "elevenlabs_voice_id": "voice_mock_xyz",
        "llm_provider": "gemini",
        "tts_provider": "sapi"
    }

    res = bridge.save_settings(payload)
    assert res.get("status") == "success"

    # Check settings on runtime object
    assert settings.GROQ_API_KEY == "gsk_test_mock_12345"
    assert settings.GEMINI_API_KEY == "AIza_mock_67890"
    assert settings.ELEVENLABS_API_KEY == "xi_mock_abcdef"
    assert settings.ELEVENLABS_VOICE_ID == "voice_mock_xyz"
    assert settings.DEFAULT_LLM_PROVIDER == "gemini"
    assert settings.TTS_PROVIDER == "sapi"

    # Check initial data returned to frontend HUD
    init_data = bridge.get_initial_data()
    assert init_data["settings"]["groq_api_key"] == "gsk_test_mock_12345"
    assert init_data["settings"]["gemini_api_key"] == "AIza_mock_67890"
    assert init_data["settings"]["elevenlabs_api_key"] == "xi_mock_abcdef"
    assert init_data["settings"]["cloned_voice_id"] == "voice_mock_xyz"

    # Check written file contents
    saved_content = test_env.read_text(encoding="utf-8")
    assert 'GROQ_API_KEY="gsk_test_mock_12345"' in saved_content
    assert 'GEMINI_API_KEY="AIza_mock_67890"' in saved_content
    assert 'DEFAULT_LLM_PROVIDER="gemini"' in saved_content

    # Restore original settings
    settings.GROQ_API_KEY = orig_groq
    settings.GEMINI_API_KEY = orig_gemini
    settings.ELEVENLABS_API_KEY = orig_el_key
    settings.ELEVENLABS_VOICE_ID = orig_el_vid
    settings.DEFAULT_LLM_PROVIDER = orig_llm
    settings.TTS_PROVIDER = orig_tts


def test_bring_sarathi_window_to_front():
    from gui.hud import bring_sarathi_window_to_front
    # Verify execution runs safely and without exceptions
    bring_sarathi_window_to_front("NON_EXISTENT_WINDOW_TITLE_12345")


def test_hud_app_wake_detected(monkeypatch):
    from gui.hud import SarathiHUDApp
    app = SarathiHUDApp()

    class MockWindow:
        def __init__(self):
            self.show_called = False
            self.restore_called = False
            self.js_calls = []

        def show(self):
            self.show_called = True

        def restore(self):
            self.restore_called = True

        def focus(self):
            pass

        def evaluate_js(self, js):
            self.js_calls.append(js)

    mock_win = MockWindow()
    app.window = mock_win
    app.is_running = True

    app._on_wake_detected()

    assert mock_win.show_called is True
    assert mock_win.restore_called is True
    assert any("wake_detected" in js for js in mock_win.js_calls)


def test_bridge_compact_expand(bridge):
    res_compact = bridge.collapse_to_compact()
    assert res_compact.get("status") == "ok"
    assert bridge.is_compact is True

    res_expand = bridge.expand_dashboard()
    assert res_expand.get("status") == "ok"
    assert bridge.is_compact is False

    res_toggle = bridge.toggle_compact_mode()
    assert res_toggle.get("status") == "ok"
    assert bridge.is_compact is True
