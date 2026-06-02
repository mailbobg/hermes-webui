# Hermes WebUI — Windows installer

Builds `Hermes-Setup-<version>.exe`: a Windows x64 installer that bundles an
embedded CPython, the WebUI, and the Hermes **agent** offline, and runs the
agent **in-process** locally. It is the Windows counterpart of the macOS
`Hermes.app` / DMG.

> ⚠️ **Must be built on Windows.** This cannot be cross-built or tested from
> macOS/Linux. All commands below run on a Windows 10/11 x64 machine.

## What gets produced

```
%LOCALAPPDATA%\Programs\Hermes\        (per-user install, no admin needed)
  ├─ python\        embedded CPython 3.12 + all deps (WebUI + agent, incl. openai)
  ├─ webui\         this repo's source
  ├─ agent\         hermes-agent source (from your local copy)
  └─ Hermes.exe     launcher (starts the server, opens the browser, cleans up)
```

Launching `Hermes.exe` starts `webui\server.py` with the embedded Python, waits
for `http://127.0.0.1:8787/`, opens your default browser, and on exit tears down
the server process tree + any background gateway.

## Build prerequisites (on Windows)

1. **Python 3.11+** on PATH (only to *run* the build/PyInstaller; the shipped
   runtime is downloaded separately). `winget install Python.Python.3.12`
2. **Inno Setup 6** — provides `iscc`. `winget install JRSoftware.InnoSetup`,
   then ensure its folder (e.g. `C:\Program Files (x86)\Inno Setup 6`) is on PATH.
3. **tar** — ships with Windows 10/11.
4. Internet access (to fetch python-build-standalone and pip wheels).

PyInstaller + psutil are installed automatically into the embedded interpreter
by the build script.

## Get the agent source onto Windows

The agent ships from **your local copy** (not a clone). On the machine that has
it (e.g. this Mac), export a clean source tree — no venv, no git, no caches:

```bash
# macOS/Linux, from the machine with ~/.hermes/hermes-agent
rsync -a --delete \
  --exclude venv --exclude .venv --exclude .git --exclude '__pycache__' --exclude '*.pyc' \
  ~/.hermes/hermes-agent/ /tmp/hermes-agent-src/
# then copy /tmp/hermes-agent-src to the Windows box, e.g. C:\src\hermes-agent
```

Only the **source** matters (`pyproject.toml`, `run_agent.py`, `gateway/`, ...);
its dependencies are reinstalled fresh on Windows from PyPI (all cross-platform).

## Build

```powershell
cd packaging\windows
.\build.ps1 -AgentSrc C:\src\hermes-agent -Version 0.1.1
# Output: packaging\windows\build\Hermes-Setup-0.1.1.exe
```

Options: `-Port 8787` (default bind port baked into the app), `-PyVersion 3.12`.

## Install & run

1. Double-click `Hermes-Setup-<ver>.exe`. It's **unsigned**, so SmartScreen will
   warn — click **More info → Run anyway**. (Sign with an Authenticode cert later
   to remove this.)
2. Installs per-user to `%LOCALAPPDATA%\Programs\Hermes` (no admin prompt).
3. Launch from Start Menu / desktop. The browser opens to the WebUI.
4. **First-time agent setup:** open Settings and configure your **deepseek**
   provider (base URL + API key + model). deepseek speaks the OpenAI-compatible
   API and is covered by the bundled `openai` SDK — no extra download.

State/sessions live under `%LOCALAPPDATA%\hermes` (`HERMES_HOME`); logs at
`%LOCALAPPDATA%\hermes\webui.log`.

## Verification checklist (run on Windows)

- [ ] `build.ps1` completes and produces `build\Hermes-Setup-<ver>.exe`.
- [ ] Installer runs; Start Menu + desktop shortcuts appear.
- [ ] `Hermes.exe` opens the browser; WebUI loads (transparent logo, file-tree
      expand/collapse, etc. all present).
- [ ] Configure deepseek in Settings → complete one chat turn successfully.
- [ ] Close the app → no leftover `python.exe` / gateway processes
      (Task Manager).
- [ ] Uninstall removes `%LOCALAPPDATA%\Programs\Hermes` cleanly.

## Known risks / things to verify and adjust on Windows

These could not be validated from macOS:

1. **python-build-standalone layout** — the Windows `install_only` tarball lays
   out `python.exe` at the root (no `bin/`). `build.ps1` assumes
   `--strip-components=1`; adjust if extraction differs. The script hard-fails
   with a clear message if `python.exe` is missing.
2. **Agent in-process load** — the WebUI resolves the agent via
   `HERMES_WEBUI_AGENT_DIR` (set by the launcher) and `config.py` injects it onto
   `sys.path`. Because no separate agent venv is created, all agent deps live in
   the embedded interpreter. Verify `import gateway` / `run_agent` succeed at
   startup (check `webui.log`). If the WebUI insists on an agent **venv**, create
   one under `agent\venv` during the build instead.
3. **Gateway shutdown** — `launcher._stop_gateway` calls
   `run_agent.py gateway stop`; confirm that's the correct CLI for stopping a
   background gateway on Windows, or adjust.
4. **Pinned native wheels** — agent deps (e.g. `cryptography`, `pydantic-core`,
   `psutil`) must have Windows x64 wheels for the bundled CPython version; pip
   resolves these automatically, but a brand-new Python minor can lag wheel
   availability. Stick to 3.12 unless you've checked wheels for the target.
5. **Antivirus / SmartScreen** — onefile PyInstaller exes are sometimes
   false-flagged; a signed launcher avoids most of this.

## Files

| File | Purpose |
|------|---------|
| `build.ps1` | Build orchestrator (fetch Python, deps, stage, compile, package). |
| `launcher.py` | Source for `Hermes.exe` (start server, open browser, cleanup). |
| `hermes.iss` | Inno Setup script (installer layout, shortcuts, uninstaller). |
| `Hermes.ico` | App icon (generated from the transparent Hermes logo). |
