"""Unit tests for api/agent_connection.py.

Covers:
  - get_agent_connection: local default, remote mode, env_override detection
  - set_agent_connection: writes correct keys for remote, clears them for local,
    preserves unrelated config keys, validates the remote URL
  - stop_gateway: hermes CLI located / not found, subprocess mocked
  - the GET/POST route wiring in api/routes.py
"""
import subprocess
from pathlib import Path

import pytest
import yaml

import api.config as config
import api.agent_connection as ac


@pytest.fixture
def cfg_path(monkeypatch, tmp_path):
    """Point the active config.yaml at a tmp file for both modules.

    HERMES_CONFIG_PATH makes config._get_config_path() resolve to our tmp file,
    so get_config()'s real mtime hot-reload reads it. We also force a reload so
    no stale in-memory cache leaks across tests.
    """
    path = tmp_path / "config.yaml"
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(path))
    # Ensure no env override leaks in from the host environment.
    monkeypatch.delenv("HERMES_WEBUI_CHAT_BACKEND", raising=False)
    monkeypatch.delenv("HERMES_WEBUI_GATEWAY_BASE_URL", raising=False)
    config.reload_config()
    yield path
    config.reload_config()


def _write_cfg(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    config.reload_config()


def _read_cfg(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ── get_agent_connection ────────────────────────────────────────────────────


def test_get_local_by_default(cfg_path):
    _write_cfg(cfg_path, {"some_other_key": "keep"})
    state = ac.get_agent_connection()
    assert state["mode"] == "local"
    assert state["env_override"] is False
    assert state["env_backend"] is None
    assert state["gateway_base_url"]  # default fallback present


def test_get_remote_when_gateway_configured(cfg_path):
    _write_cfg(
        cfg_path,
        {
            "webui_chat_backend": "gateway",
            "webui_gateway_base_url": "http://10.0.0.5:8642",
        },
    )
    state = ac.get_agent_connection()
    assert state["mode"] == "remote"
    assert state["gateway_base_url"] == "http://10.0.0.5:8642"
    assert state["env_override"] is False


def test_get_env_override_detected(cfg_path, monkeypatch):
    _write_cfg(cfg_path, {})
    monkeypatch.setenv("HERMES_WEBUI_CHAT_BACKEND", "gateway")
    state = ac.get_agent_connection()
    assert state["env_override"] is True
    assert state["env_backend"] == "gateway"
    # env forces gateway → effective mode is remote even though config is empty
    assert state["mode"] == "remote"


# ── set_agent_connection ────────────────────────────────────────────────────


def test_set_remote_writes_keys(cfg_path):
    _write_cfg(cfg_path, {"unrelated": "value"})
    result = ac.set_agent_connection("remote", "http://gw.local:8642/")
    assert result == {"ok": True, "mode": "remote"}
    data = _read_cfg(cfg_path)
    assert data["webui_chat_backend"] == "gateway"
    # trailing slash normalized away
    assert data["webui_gateway_base_url"] == "http://gw.local:8642"
    # unrelated keys preserved
    assert data["unrelated"] == "value"


def test_set_local_clears_gateway_keys(cfg_path):
    _write_cfg(
        cfg_path,
        {
            "webui_chat_backend": "gateway",
            "webui_gateway_base_url": "http://x:8642",
            "keep_me": 1,
        },
    )
    result = ac.set_agent_connection("local")
    assert result == {"ok": True, "mode": "local"}
    data = _read_cfg(cfg_path)
    assert "webui_chat_backend" not in data
    assert "webui_gateway_base_url" not in data
    assert data["keep_me"] == 1


def test_set_remote_requires_valid_url(cfg_path):
    _write_cfg(cfg_path, {})
    with pytest.raises(ac.AgentConnectionError):
        ac.set_agent_connection("remote", "")
    with pytest.raises(ac.AgentConnectionError):
        ac.set_agent_connection("remote", "ftp://bad")
    with pytest.raises(ac.AgentConnectionError):
        ac.set_agent_connection("remote", "not-a-url")


def test_set_invalid_mode_raises(cfg_path):
    _write_cfg(cfg_path, {})
    with pytest.raises(ac.AgentConnectionError):
        ac.set_agent_connection("sideways")


def test_set_then_get_round_trips(cfg_path):
    _write_cfg(cfg_path, {})
    ac.set_agent_connection("remote", "http://host:9000")
    assert ac.get_agent_connection()["mode"] == "remote"
    ac.set_agent_connection("local")
    assert ac.get_agent_connection()["mode"] == "local"


# ── stop_gateway ────────────────────────────────────────────────────────────


def test_stop_gateway_cli_not_found(monkeypatch):
    monkeypatch.setattr(ac.shutil, "which", lambda _: None)
    monkeypatch.setattr(ac.Path, "home", staticmethod(lambda: Path("/nonexistent-home")))
    res = ac.stop_gateway()
    assert res["ok"] is False
    assert "not found" in res["detail"]


def test_stop_gateway_runs_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(ac.shutil, "which", lambda _: "/usr/bin/hermes")
    monkeypatch.setattr(ac, "get_active_hermes_home", lambda: tmp_path)

    captured = {}

    class _Proc:
        returncode = 0
        stdout = "gateway stopped"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        captured["timeout"] = kwargs.get("timeout")
        return _Proc()

    monkeypatch.setattr(ac.subprocess, "run", _fake_run)
    res = ac.stop_gateway()
    assert res == {"ok": True, "detail": "gateway stopped"}
    assert captured["cmd"] == ["/usr/bin/hermes", "gateway", "stop"]
    assert captured["env"]["HERMES_HOME"] == str(tmp_path)
    assert captured["timeout"] == 30


def test_stop_gateway_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(ac.shutil, "which", lambda _: "/usr/bin/hermes")
    monkeypatch.setattr(ac, "get_active_hermes_home", lambda: tmp_path)

    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="hermes", timeout=30)

    monkeypatch.setattr(ac.subprocess, "run", _raise)
    res = ac.stop_gateway()
    assert res["ok"] is False
    assert "timed out" in res["detail"]


def test_stop_gateway_nonzero_returncode(monkeypatch, tmp_path):
    monkeypatch.setattr(ac.shutil, "which", lambda _: "/usr/bin/hermes")
    monkeypatch.setattr(ac, "get_active_hermes_home", lambda: tmp_path)

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "no gateway running"

    monkeypatch.setattr(ac.subprocess, "run", lambda *a, **k: _Proc())
    res = ac.stop_gateway()
    assert res["ok"] is False
    assert res["detail"] == "no gateway running"


# ── route wiring ────────────────────────────────────────────────────────────


def test_routes_register_agent_connection_endpoints():
    src = Path("api/routes.py").read_text(encoding="utf-8")
    assert '"/api/agent-connection"' in src
    assert '"/api/gateway/stop"' in src
    assert "from api.agent_connection import get_agent_connection" in src
    assert "set_agent_connection" in src
    assert "stop_gateway" in src
