"""Backend for the System-panel "Agent connection" controls.

Two responsibilities, both pure (no HTTP/routing concerns — that lives in the
routes layer):

  1. Agent connection (local vs remote gateway): read/write the two config.yaml
     keys (``webui_chat_backend`` / ``webui_gateway_base_url``) that decide
     whether browser chat runs in-process (local, default) or bridges to a
     remote Hermes Gateway API server. Writes are picked up immediately by the
     chat dispatch path because it reads config via ``get_config()``, which has
     mtime-based hot reload — no restart required.

  2. Stop the background Hermes Agent gateway (``hermes gateway stop``), mirroring
     the pattern in ``api/platforms/feishu.py``'s ``restart_gateway()``.

Environment variables ``HERMES_WEBUI_CHAT_BACKEND`` / ``HERMES_WEBUI_GATEWAY_BASE_URL``
override config.yaml at runtime (see ``api/gateway_chat.py``). When either is
set, edits made here will not take effect, so ``get_agent_connection()`` reports
``env_override`` for the frontend to warn about.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from api.config import (
    _get_config_path,
    _load_yaml_config_file,
    _save_yaml_config_file,
    get_config,
)
from api.gateway_chat import (
    _WEBUI_CHAT_BACKEND_ENV,
    _WEBUI_GATEWAY_BASE_URL_ENV,
    _gateway_base_url,
    webui_chat_backend_mode,
)
from api.profiles import get_active_hermes_home

_DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8642"


class AgentConnectionError(ValueError):
    """Raised on invalid agent-connection input."""


def _validate_gateway_url(raw: object) -> str:
    """Return a normalized http(s) gateway base URL or raise.

    Trailing slashes are stripped so the value matches how
    ``gateway_chat.py`` consumes ``webui_gateway_base_url``.
    """
    url = str(raw or "").strip()
    if not url:
        raise AgentConnectionError("gateway_base_url is required for remote mode")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise AgentConnectionError("gateway_base_url must start with http:// or https://")
    if not parsed.netloc:
        raise AgentConnectionError("gateway_base_url must include a host")
    return url.rstrip("/")


def get_agent_connection() -> dict:
    """Return the current agent-connection state for the System panel.

    Reuses ``webui_chat_backend_mode`` / ``_gateway_base_url`` from
    ``gateway_chat.py`` so the reported mode matches what chat dispatch actually
    does. ``mode`` is the *effective* mode (env overrides included). When an env
    var forces the backend, ``env_override`` is True and edits here won't apply
    until that env var is unset.
    """
    cfg = get_config()
    mode = "remote" if webui_chat_backend_mode(cfg) == "gateway" else "local"
    env_backend = os.environ.get(_WEBUI_CHAT_BACKEND_ENV)
    env_base_url = os.environ.get(_WEBUI_GATEWAY_BASE_URL_ENV)
    env_override = bool(
        (env_backend or "").strip() or (env_base_url or "").strip()
    )
    return {
        "mode": mode,
        "gateway_base_url": _gateway_base_url(cfg) or _DEFAULT_GATEWAY_BASE_URL,
        "env_override": env_override,
        "env_backend": (env_backend or None),
    }


def set_agent_connection(mode: object, gateway_base_url: object = None) -> dict:
    """Persist the agent-connection choice to config.yaml.

    remote → ``webui_chat_backend: gateway`` + ``webui_gateway_base_url: <url>``.
    local  → remove both keys so chat falls back to the in-process runtime.

    Only those two keys are touched; every other config value is preserved. The
    change is effective immediately (config.yaml hot-reload via get_config()),
    unless an env var override is in effect.
    """
    normalized = str(mode or "").strip().lower()
    if normalized not in {"local", "remote"}:
        raise AgentConnectionError("mode must be 'local' or 'remote'")

    config_path = _get_config_path()
    config_data = _load_yaml_config_file(config_path)

    if normalized == "remote":
        url = _validate_gateway_url(gateway_base_url)
        config_data["webui_chat_backend"] = "gateway"
        config_data["webui_gateway_base_url"] = url
    else:
        # Local: drop the gateway keys entirely so the default in-process path
        # is restored. Use pop so a missing key is a no-op.
        config_data.pop("webui_chat_backend", None)
        config_data.pop("webui_gateway_base_url", None)

    _save_yaml_config_file(config_path, config_data)
    return {"ok": True, "mode": normalized}


def _resolve_hermes_cli() -> str | None:
    """Locate the hermes CLI via PATH then ``~/.local/bin/hermes``."""
    hermes = shutil.which("hermes")
    if hermes:
        return hermes
    fallback = Path.home() / ".local" / "bin" / "hermes"
    if fallback.exists():
        return str(fallback)
    return None


def stop_gateway() -> dict:
    """Run ``hermes gateway stop`` targeting the active profile.

    Stops the background Hermes Agent gateway (messaging platforms / cron). Does
    NOT affect the WebUI server process. Mirrors ``feishu.restart_gateway()``;
    never raises for an operational failure — always returns ``{ok, detail}``.
    """
    hermes = _resolve_hermes_cli()
    if not hermes:
        return {"ok": False, "detail": "hermes CLI not found"}

    env = {**os.environ, "HERMES_HOME": str(get_active_hermes_home())}
    try:
        proc = subprocess.run(
            [hermes, "gateway", "stop"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": "hermes gateway stop timed out"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}

    detail = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    return {"ok": proc.returncode == 0, "detail": detail}
