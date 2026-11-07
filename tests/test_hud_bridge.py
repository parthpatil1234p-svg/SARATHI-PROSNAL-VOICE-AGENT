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
