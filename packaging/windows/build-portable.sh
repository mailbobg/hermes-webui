#!/usr/bin/env bash
# Build a Windows x64 PORTABLE bundle (zip) FROM macOS/Linux — no Windows needed.
#
# Cross-builds everything: Windows embeddable CPython + cross-downloaded
# Windows wheels (WebUI + agent core deps) + WebUI/agent sources + a
# cross-compiled Hermes.exe launcher (zig). The agent runs in-process from the
# bundled source; deepseek is covered by the bundled `openai` SDK.
#
# Usage:  ./build-portable.sh [AGENT_SRC] [VERSION]
#   AGENT_SRC  hermes-agent source dir (default: ~/.hermes/hermes-agent)
#   VERSION    version string for the zip name (default: 0.1.1)
#
# Output:  packaging/windows/build-portable/Hermes-Windows-Portable-<ver>.zip
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
AGENT_SRC="${1:-$HOME/.hermes/hermes-agent}"
VERSION="${2:-0.1.1}"
PYVER="3.12.7"
HOSTPY="${HOSTPY:-/opt/homebrew/bin/python3}"

BUILD="$HERE/build-portable"
STAGE="$BUILD/Hermes"
CACHE="$HERE/.cache-portable"

command -v zig >/dev/null || { echo "zig not found (brew install zig)"; exit 1; }
[ -f "$AGENT_SRC/pyproject.toml" ] || { echo "AGENT_SRC '$AGENT_SRC' has no pyproject.toml"; exit 1; }

rm -rf "$STAGE"; mkdir -p "$STAGE" "$CACHE"

echo "==> Windows embeddable CPython $PYVER"
EMBED_ZIP="$CACHE/python-$PYVER-embed-amd64.zip"
[ -f "$EMBED_ZIP" ] || curl -fSL "https://www.python.org/ftp/python/$PYVER/python-$PYVER-embed-amd64.zip" -o "$EMBED_ZIP"
mkdir -p "$STAGE/python"
unzip -oq "$EMBED_ZIP" -d "$STAGE/python"

# Enable site-packages so our cross-installed deps are importable.
cat > "$STAGE/python/python312._pth" <<'PTHEOF'
python312.zip
.
Lib\site-packages
import site
PTHEOF
mkdir -p "$STAGE/python/Lib/site-packages"

echo "==> Cross-installing Windows wheels (win_amd64, cp312)"
# WebUI deps come from requirements.txt — single source of truth, shared with
# build.ps1 / macos build.sh, so they can't drift. Agent core deps are listed
# explicitly because a --platform cross-install can't resolve them from the
# agent's local source tree; keep this in sync with hermes-agent's
# pyproject.toml [dependencies]. deepseek needs no extra — it speaks the
# OpenAI-compatible API via `openai`.
AGENT_DEPS=(
  openai python-dotenv fire "httpx[socks]" rich tenacity ruamel.yaml
  requests jinja2 pydantic prompt_toolkit croniter "PyJWT[crypto]" tzdata psutil
)
"$HOSTPY" -m pip install \
  --target "$STAGE/python/Lib/site-packages" \
  --platform win_amd64 --python-version 312 --implementation cp --abi cp312 \
  --only-binary=:all: --upgrade \
  -r "$REPO_ROOT/requirements.txt" "${AGENT_DEPS[@]}"

echo "==> Copying WebUI + agent sources"
rsync -a --delete \
  --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'tests' --exclude 'docs' \
  --exclude 'packaging/macos/build' --exclude 'packaging/macos/.python-cache' \
  --exclude 'packaging/windows/build' --exclude 'packaging/windows/build-portable' \
  --exclude 'packaging/windows/.cache-portable' --exclude 'node_modules' \
  "$REPO_ROOT/" "$STAGE/webui/"
rsync -a --delete \
  --exclude 'venv' --exclude '.venv' --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
  "$AGENT_SRC/" "$STAGE/agent/"

echo "==> Cross-compiling Hermes.exe"
zig cc -target x86_64-windows-gnu "$HERE/launcher.c" -o "$STAGE/Hermes.exe" -lshell32

echo "==> Zipping"
OUT="$BUILD/Hermes-Windows-Portable-$VERSION.zip"
rm -f "$OUT"
( cd "$BUILD" && zip -rqy "Hermes-Windows-Portable-$VERSION.zip" "Hermes" )

echo "Done -> $OUT"
du -sh "$OUT"
