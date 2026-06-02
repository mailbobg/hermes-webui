#requires -version 5.1
<#
.SYNOPSIS
  Build a Windows x64 installer (Hermes-Setup-<ver>.exe) for Hermes WebUI with
  the Hermes agent bundled offline. RUN THIS ON A WINDOWS MACHINE.

.DESCRIPTION
  Windows counterpart of packaging/macos/build.sh. Steps:
    1. Fetch a relocatable CPython (python-build-standalone, win x64).
    2. pip install WebUI deps + the agent (core deps; deepseek via openai SDK).
    3. Stage WebUI + agent sources (junk excluded).
    4. Strip stray __pycache__ (same defense as the macOS signing fix).
    5. Compile launcher.py -> Hermes.exe with PyInstaller.
    6. Package staging into setup.exe with Inno Setup (iscc).

.PARAMETER AgentSrc
  Path to a hermes-agent SOURCE checkout (dir with pyproject.toml / run_agent.py
  / gateway). Required. Copy it from your Mac/another machine first; its venv,
  .git and __pycache__ are excluded automatically.

.PARAMETER Version
  Version string baked into the installer. Default: `git describe` or 0.0.0.

.PARAMETER Port
  Default TCP port the installed app binds to. Default: 8787.

.PARAMETER PyVersion
  CPython minor series to bundle. Default: 3.12.

.EXAMPLE
  .\build.ps1 -AgentSrc C:\src\hermes-agent -Version 0.1.1
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$AgentSrc,
  [string]$Version = "",
  [int]$Port = 8787,
  [string]$PyVersion = "3.12"
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $PSCommandPath
$RepoRoot = (Resolve-Path (Join-Path $Here "..\..")).Path
$Build = Join-Path $Here "build"
$Staging = Join-Path $Build "staging"
$Cache = Join-Path $Here ".python-cache"

function Say($m) { Write-Host "> $m" -ForegroundColor Cyan }

# ---- Validate inputs --------------------------------------------------------
if (-not (Test-Path (Join-Path $AgentSrc "pyproject.toml"))) {
  throw "AgentSrc '$AgentSrc' is not a hermes-agent source dir (no pyproject.toml)."
}
foreach ($tool in @("tar", "iscc")) {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
    throw "Required tool '$tool' not found on PATH. (tar ships with Win10+; iscc is Inno Setup 6.)"
  }
}
if (-not $Version) {
  try { $Version = (git -C $RepoRoot describe --tags --always 2>$null) } catch {}
  if (-not $Version) { $Version = "0.0.0" }
}
$VerClean = ($Version -replace '^v', '')

# ---- 1. Fetch relocatable CPython (win x64) ---------------------------------
Say "Resolving python-build-standalone ($PyVersion, x86_64-pc-windows-msvc)..."
New-Item -ItemType Directory -Force -Path $Cache | Out-Null
$relApi = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
$rel = Invoke-RestMethod -Uri $relApi -Headers @{ "User-Agent" = "hermes-build" }
$pattern = "cpython-$([regex]::Escape($PyVersion))\.\d+(\+|%2B|\.)\d+.*-x86_64-pc-windows-msvc-install_only(-stripped)?\.tar\.gz$"
$asset = $rel.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
if (-not $asset) { throw "No CPython $PyVersion windows x64 install_only asset found in latest release." }
$tarball = Join-Path $Cache $asset.name
if (-not (Test-Path $tarball)) {
  Say "Downloading $($asset.name)"
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tarball
}

# ---- 2. Reset staging, extract python ---------------------------------------
Say "Staging..."
if (Test-Path $Staging) { Remove-Item -Recurse -Force $Staging }
New-Item -ItemType Directory -Force -Path $Staging | Out-Null
$PyDir = Join-Path $Staging "python"
New-Item -ItemType Directory -Force -Path $PyDir | Out-Null
# install_only tarballs extract as python/* ; strip that leading component.
tar -xzf $tarball -C $PyDir --strip-components=1
$PyExe = Join-Path $PyDir "python.exe"
if (-not (Test-Path $PyExe)) {
  throw "python.exe not found at $PyExe after extract. Inspect the python-build-standalone Windows layout and adjust --strip-components."
}

# ---- 3. Install deps into the embedded interpreter --------------------------
Say "Installing WebUI deps"
& $PyExe -m pip install --upgrade pip
& $PyExe -m pip install -r (Join-Path $RepoRoot "requirements.txt")
Say "Installing hermes-agent (core deps; deepseek via openai SDK)"
& $PyExe -m pip install "$AgentSrc"

# ---- 4. Copy sources (exclude junk) -----------------------------------------
Say "Copying WebUI + agent sources"
$WebuiDst = Join-Path $Staging "webui"
$AgentDst = Join-Path $Staging "agent"
# robocopy exit codes 0-7 are success; treat >=8 as failure.
function Robo($src, $dst, $xd, $xf) {
  $args = @($src, $dst, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
  if ($xd) { $args += "/XD"; $args += $xd }
  if ($xf) { $args += "/XF"; $args += $xf }
  robocopy @args | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy $src -> $dst failed (code $LASTEXITCODE)" }
}
Robo $RepoRoot $WebuiDst `
  @("$RepoRoot\.git", "$RepoRoot\packaging\windows\build", "$RepoRoot\packaging\windows\.python-cache", "$RepoRoot\packaging\macos\build", "$RepoRoot\packaging\macos\.python-cache", "node_modules", "__pycache__", ".venv", "venv") `
  @("*.pyc")
Robo $AgentSrc $AgentDst @(".git", "__pycache__", "venv", ".venv") @("*.pyc")

# ---- 5. Strip stray __pycache__ (defense) -----------------------------------
Say "Stripping __pycache__ from staging"
Get-ChildItem -Path $Staging -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ---- 6. Compile launcher exe ------------------------------------------------
Say "Compiling launcher (Hermes.exe) with PyInstaller"
& $PyExe -m pip install pyinstaller psutil
$icon = Join-Path $Here "Hermes.ico"
& $PyExe -m PyInstaller --onefile --noconsole --clean --name Hermes `
  --icon "$icon" `
  --distpath "$Staging" `
  --workpath (Join-Path $Build "pyi-work") `
  --specpath (Join-Path $Build "pyi-spec") `
  (Join-Path $Here "launcher.py")
if (-not (Test-Path (Join-Path $Staging "Hermes.exe"))) { throw "PyInstaller did not produce Hermes.exe" }

# ---- 7. Package with Inno Setup ---------------------------------------------
Say "Packaging with Inno Setup"
$iss = Join-Path $Here "hermes.iss"
& iscc "/DAppVersion=$VerClean" "/DStaging=$Staging" "/DPort=$Port" "/DOutputDir=$Build" "$iss"
if ($LASTEXITCODE -ne 0) { throw "iscc failed (code $LASTEXITCODE)" }

Say "Done -> $Build\Hermes-Setup-$VerClean.exe"
