param()
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create virtual environment' }
}
& $taskPython -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install dependencies' }
& $taskPython tools\collect_notices.py
if ($LASTEXITCODE -ne 0) { throw 'Failed to collect notices' }
& $taskPython -m PyInstaller --noconfirm ScreenshotOCR.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Get-Item -LiteralPath (Join-Path $PSScriptRoot 'dist\ScreenshotOCR.exe') | Select-Object FullName,Length
