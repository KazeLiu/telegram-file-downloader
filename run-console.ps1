$ErrorActionPreference = "Stop"
$PythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Run setup.ps1 first."
}
& $PythonExe -m telegram_file_watcher

