$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$VenvDir = Join-Path $ProjectDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PythonwExe = Join-Path $VenvDir "Scripts\pythonw.exe"

Write-Host "Setting up Telegram File Watcher..." -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $PythonExe)) {
    py -3.12 -m venv $VenvDir
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -e $ProjectDir

Write-Host ""
& $PythonExe -m telegram_file_watcher.configure
if ($LASTEXITCODE -ne 0) {
    throw "Telegram configuration did not complete."
}

$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "Telegram File Watcher.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PythonwExe
$Shortcut.Arguments = "-m telegram_file_watcher"
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description = "Download new files from the configured Telegram group"
$Shortcut.Save()

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "The watcher will start automatically when you next sign in to Windows."
Write-Host "Starting it now..."
Start-Process -FilePath $PythonwExe -ArgumentList "-m", "telegram_file_watcher" -WorkingDirectory $ProjectDir -WindowStyle Hidden

