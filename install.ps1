<#
.SYNOPSIS
    Install, update or uninstall GazeFocus for the current user (no admin rights needed).

.DESCRIPTION
    Installs uv if it's missing, downloads GazeFocus (the latest release, or -Ref), sets up its Python
    environment and the face model, adds a Start-menu shortcut, and starts it. Running it again updates.
    Your settings and calibration live in %APPDATA%\GazeFocus and are never touched.

.EXAMPLE
    irm https://raw.githubusercontent.com/1nourhacker1/GazeFocus/main/install.ps1 | iex

.EXAMPLE
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/1nourhacker1/GazeFocus/main/install.ps1))) -Startup
    Also starts GazeFocus at login.

.EXAMPLE
    & ([scriptblock]::Create((irm https://raw.githubusercontent.com/1nourhacker1/GazeFocus/main/install.ps1))) -Uninstall
#>
param(
    [string]$Dir = (Join-Path $env:LOCALAPPDATA "Programs\GazeFocus"),
    [string]$Ref = "",  # a release tag or a branch; empty: the latest release, else main
    [switch]$Startup,
    [switch]$Uninstall,
    [switch]$NoStart,
    [switch]$NoShortcut,
    [string]$ShortcutDir = [Environment]::GetFolderPath("Programs")
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is far faster without the progress bar
$Repo = "1nourhacker1/GazeFocus"
$Exe = Join-Path $Dir ".venv\Scripts\gazefocus-app.exe"
$StartupDir = [Environment]::GetFolderPath("Startup")

function Say($text) { Write-Host "GazeFocus: $text" }

function Test-Running {
    # running = one of the environment's programs is locked by a process (whatever form its path was started with)
    foreach ($name in @("gazefocus-app.exe", "gazefocus.exe", "pythonw.exe", "python.exe")) {
        $file = Join-Path $Dir ".venv\Scripts\$name"
        if (Test-Path $file) {
            try { [IO.File]::Open($file, "Open", "ReadWrite", "None").Close() }
            catch { return $true }
        }
    }
    return $false
}

function New-Shortcut($folder) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $folder "GazeFocus.lnk"))
    $link.TargetPath = $Exe
    $link.WorkingDirectory = $Dir
    $link.Description = "Focus follows your gaze"
    $link.Save()
}

if ($env:OS -ne "Windows_NT") { throw "GazeFocus runs on Windows only." }

if (Test-Running) {
    Say "it's running. Quit it from its tray icon (right-click, Quit), then run this again."
    return
}

if ($Uninstall) {
    foreach ($folder in @($ShortcutDir, $StartupDir)) {
        $link = Join-Path $folder "GazeFocus.lnk"
        if (Test-Path $link) { Remove-Item $link -Force }
    }
    if (Test-Path $Dir) { Remove-Item $Dir -Recurse -Force }
    Say "uninstalled. Your settings and calibration are still in $env:APPDATA\GazeFocus (delete that folder to remove them too)."
    return
}

# uv: it brings the Python 3.12 that MediaPipe needs
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Say "installing uv (https://docs.astral.sh/uv/)..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv didn't install; see https://docs.astral.sh/uv/" }
}

if (-not $Ref) {
    try { $Ref = (Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest").tag_name }
    catch { $Ref = "main" }
}
Say "downloading $Ref..."
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("gazefocus-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $zip = Join-Path $tmp "src.zip"
    Invoke-WebRequest "https://github.com/$Repo/archive/$Ref.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath (Join-Path $tmp "src")
    $src = Get-ChildItem (Join-Path $tmp "src") -Directory | Select-Object -First 1

    # an update keeps the environment and the model, so it only downloads what changed
    $keep = Join-Path $tmp "keep"
    New-Item -ItemType Directory -Path $keep | Out-Null
    if (Test-Path $Dir) {
        foreach ($name in @(".venv", "models")) {
            if (Test-Path (Join-Path $Dir $name)) { Move-Item (Join-Path $Dir $name) $keep }
        }
        Remove-Item $Dir -Recurse -Force
    }
    New-Item -ItemType Directory -Path (Split-Path $Dir) -Force | Out-Null
    Move-Item $src.FullName $Dir
    Get-ChildItem $keep | ForEach-Object { Move-Item $_.FullName $Dir }
}
finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

Push-Location $Dir
try {
    Say "setting up Python and the packages (the first time takes a minute)..."
    uv sync --frozen --no-dev --quiet
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    Say "fetching the face model..."
    uv run --frozen --no-dev python scripts/fetch_model.py
    if ($LASTEXITCODE -ne 0) { throw "the face model didn't download" }
}
finally {
    Pop-Location
}

if (-not $NoShortcut) {
    New-Shortcut $ShortcutDir
    if ($Startup) { New-Shortcut $StartupDir; Say "it will start at login." }
}
Say "installed $Ref in $Dir."
if (-not $NoStart) {
    Start-Process $Exe -WorkingDirectory $Dir
    Say "started: look for the dock under your laptop camera. The first start opens the calibration."
}
