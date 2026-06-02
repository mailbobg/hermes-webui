"""Hermes WebUI — Windows launcher.

Compiled to ``Hermes.exe`` with PyInstaller. It lives at the install root next
to ``python\\``, ``webui\\`` and ``agent\\``. Responsibilities:

  1. Point the WebUI at the bundled embedded Python and agent source.
  2. Start ``webui\\server.py`` with the embedded interpreter (no console).
  3. Wait until the HTTP server answers, then open the default browser.
  4. On exit, tear down the server process tree (psutil) and best-effort stop
     any background Hermes gateway the agent may have spawned.

This is the Windows counterpart of packaging/macos/supervisor.py + the Swift
shell, collapsed into one small launcher.
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
import urllib.request
import webbrowser
from pathlib import Path


def _install_root() -> Path:
    # When frozen by PyInstaller, sys.executable is <install>\Hermes.exe.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = _install_root()
PYTHON = ROOT / "python" / "python.exe"
WEBUI = ROOT / "webui"
AGENT = ROOT / "agent"
SERVER = WEBUI / "server.py"

HOST = os.environ.get("HERMES_WEBUI_HOST", "127.0.0.1")
PORT = int(os.environ.get("HERMES_WEBUI_PORT", "8787"))


def _local_app_data() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "hermes"


def _build_env() -> dict:
    env = dict(os.environ)
    env["HERMES_HOME"] = env.get("HERMES_HOME") or str(_local_app_data())
    # config.py (_discover_agent_dir) prefers HERMES_WEBUI_AGENT_DIR and injects
    # it onto the FRONT of sys.path, so the WebUI can `import gateway`/run_agent
    # in-process from the bundled agent source.
    env.setdefault("HERMES_WEBUI_AGENT_DIR", str(AGENT))
    env.setdefault("HERMES_WEBUI_HOST", HOST)
    env.setdefault("HERMES_WEBUI_PORT", str(PORT))
    # No separate agent venv is created — every dependency (WebUI + agent) lives
    # in this embedded interpreter. Tell the WebUI to reuse it for any helper it
    # launches, instead of hunting for an agent venv that does not exist.
    env["HERMES_WEBUI_PYTHON"] = str(PYTHON)
    return env


def _wait_until_up(timeout: float = 90.0) -> bool:
    url = f"http://{HOST}:{PORT}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _terminate_tree(proc: subprocess.Popen) -> None:
    try:
        import psutil  # bundled into the launcher exe
    except Exception:
        psutil = None
    if psutil is not None:
        try:
            parent = psutil.Process(proc.pid)
            procs = parent.children(recursive=True) + [parent]
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass
            _gone, alive = psutil.wait_procs(procs, timeout=8)
            for p in alive:
                try:
                    p.kill()
                except Exception:
                    pass
            return
        except Exception:
            pass
    try:
        proc.terminate()
    except Exception:
        pass


def _stop_gateway(env: dict) -> None:
    # Best-effort: if the agent started a background gateway, stop it so nothing
    # lingers after the window closes. Failure here is harmless.
    run_agent = AGENT / "run_agent.py"
    if not run_agent.exists():
        return
    try:
        subprocess.run(
            [str(PYTHON), str(run_agent), "gateway", "stop"],
            cwd=str(AGENT), env=env, timeout=30,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def main() -> int:
    if not PYTHON.exists():
        sys.stderr.write(f"Embedded Python not found: {PYTHON}\n")
        return 2
    if not SERVER.exists():
        sys.stderr.write(f"WebUI server not found: {SERVER}\n")
        return 2

    env = _build_env()
    log_dir = Path(env["HERMES_HOME"])
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "webui.log"

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with open(log_path, "ab") as logf:
        proc = subprocess.Popen(
            [str(PYTHON), str(SERVER)],
            cwd=str(WEBUI), env=env,
            stdout=logf, stderr=logf,
            creationflags=creationflags,
        )

    try:
        if _wait_until_up():
            webbrowser.open(f"http://{HOST}:{PORT}/")
        else:
            sys.stderr.write("WebUI did not become healthy in time; see webui.log\n")
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            _terminate_tree(proc)
        _stop_gateway(env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
