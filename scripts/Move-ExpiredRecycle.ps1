[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [switch]$InstallTask,
    [switch]$ListOnly
)

$ErrorActionPreference = 'Stop'
$Config = (Resolve-Path -LiteralPath $Config).ProviderPath
$settings = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $settings.container -or -not $settings.mounts) { throw 'Configure container and mounts first.' }

if ($InstallTask) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute "$PSHOME\powershell.exe" -Argument "-NoProfile -STA -WindowStyle Hidden -File `"$PSCommandPath`" -Config `"$Config`""
    $triggers = @((New-ScheduledTaskTrigger -Daily -At '09:00'), (New-ScheduledTaskTrigger -AtLogOn -User $identity))
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $options = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
    Register-ScheduledTask -TaskName 'Telegram Collector Recycle Handoff' -Action $action -Trigger $triggers -Principal $principal -Settings $options -Description 'Move application recycle files idle for 15 days into this Windows user Recycle Bin.' -Force | Out-Null
    Write-Output 'Installed: daily at 09:00 and at logon, under the current Windows user.'
    exit 0
}

if ([Threading.Thread]::CurrentThread.ApartmentState -ne 'STA') { throw 'Run with powershell.exe -STA.' }
Add-Type -Path (Join-Path $PSScriptRoot 'WindowsRecycle.cs')
$utf8 = New-Object Text.UTF8Encoding($false)
$log = Join-Path (Split-Path -Parent $Config) 'windows-recycle.log'

function Invoke-Handoff([string[]]$Arguments) {
    $output = & docker exec $settings.container python -m telegram_file_downloader.windows_recycle @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker handoff failed: $($Arguments -join ' ')" }
    return (($output -join "`n") | ConvertFrom-Json)
}

function Assert-RegularPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing a linked path: $current" }
        }
        $parent = Split-Path -Parent $current
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Get-HostRoot([string]$Directory, $Mounts) {
    $mapping = $settings.mounts.PSObject.Properties | Where-Object {
        $Directory -eq $_.Name -or $Directory.StartsWith($_.Name.TrimEnd('/') + '/', [StringComparison]::Ordinal)
    } | Sort-Object { $_.Name.Length } -Descending | Select-Object -First 1
    if (-not $mapping) { throw "No Windows mount mapping configured for $Directory" }
    $mount = $Mounts | Where-Object { $_.Destination -eq $mapping.Name } | Select-Object -First 1
    if (-not $mount -or $mount.Type -ne 'bind' -or -not $mount.RW) { throw "Expected a writable Docker bind mount at $($mapping.Name)" }
    $base = [IO.Path]::GetFullPath([string]$mapping.Value)
    $relative = $Directory.Substring($mapping.Name.Length).TrimStart('/')
    $root = [IO.Path]::GetFullPath((Join-Path $base $relative))
    if ($root -ne $base -and -not $root.StartsWith($base.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Mapped root escapes the configured Windows directory.'
    }
    $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($root))
    if ($root.StartsWith('\\') -or $drive.DriveType -ne [IO.DriveType]::Fixed) { throw 'Windows handoff requires a local fixed drive, not a network share.' }
    Assert-RegularPath $root
    return $root
}

function Write-Log([string]$Text) {
    $line = "$(Get-Date -Format o) $Text"
    [IO.File]::AppendAllText($log, $line + [Environment]::NewLine, $utf8)
    Write-Output $line
}

$mutex = New-Object Threading.Mutex($false, 'Global\TelegramCollectorRecycleHandoff')
if (-not $mutex.WaitOne(0)) { throw 'Another recycle handoff is already running.' }
$failed = $false
try {
    $inspect = & docker inspect $settings.container
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the configured Docker container.' }
    $mounts = (($inspect -join "`n") | ConvertFrom-Json)[0].Mounts
    $listing = Invoke-Handoff -Arguments @('list')
    foreach ($problem in $listing.errors) {
        $failed = $true
        Write-Log "DIRECTORY_FAILED root=$($problem.root) directory=$($problem.directory) $($problem.error)"
    }
    $items = $listing.items
    foreach ($item in $items) {
        $claimed = $false
        $confirmed = $false
        $hostFile = $null
        try {
            $root = Get-HostRoot $item.directory $mounts
            if ($ListOnly) { Write-Output "root=$($item.root) id=$($item.id) $root $($item.original) [$($item.state)]"; continue }
            $ticket = Invoke-Handoff -Arguments @('claim', '--root', $item.root, '--id', $item.id)
            $claimed = $true
            if ($ticket.id -ne $item.id -or $ticket.path -ne ".tg-trash/files/$($item.id)") { throw 'Invalid handoff ticket.' }
            $ticketPath = Join-Path $root ".tg-trash\handoff\$($item.id).json"
            Assert-RegularPath $ticketPath
            $shared = Get-Content -LiteralPath $ticketPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($shared.nonce -ne $ticket.nonce) { throw 'Mount mapping does not point to the directory confirmed by Docker.' }
            $hostFile = Join-Path $root ($ticket.path.Replace('/', '\'))
            $receiptPath = Join-Path $root ".tg-trash\handoff\$($item.id).receipt.json"
            Assert-RegularPath $hostFile
            Assert-RegularPath $receiptPath
            if (Test-Path -LiteralPath $receiptPath) {
                $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $confirmed = $receipt.nonce -eq $ticket.nonce -and [bool]$receipt.destination
            }
            if (-not (Test-Path -LiteralPath $hostFile)) {
                if (-not $confirmed) { throw 'Missing or mismatched Windows receipt; check the system Recycle Bin manually.' }
            } else {
                if ($confirmed) { throw 'A file returned after Windows confirmed the transfer; kept for manual recovery.' }
                $file = Get-Item -LiteralPath $hostFile -Force
                $modified = ([DateTimeOffset]$file.LastWriteTimeUtc).ToUnixTimeMilliseconds() / 1000.0
                if ($file.PSIsContainer -or $file.Length -ne $ticket.size -or [Math]::Abs($modified - $ticket.mtime) -gt 0.01) { throw 'The claimed file has changed; kept in the application recycle bin.' }
                $destination = [WindowsRecycle]::Move($hostFile)
                $confirmed = $true
                $receipt = @{ nonce = $ticket.nonce; destination = $destination; original = $ticket.original; transferred = (Get-Date -Format o) }
                $temporary = "$receiptPath.tmp"
                Assert-RegularPath $temporary
                [IO.File]::WriteAllText($temporary, ($receipt | ConvertTo-Json), $utf8)
                Move-Item -LiteralPath $temporary -Destination $receiptPath -Force
            }
            Invoke-Handoff -Arguments @('done', '--root', $item.root, '--id', $item.id) | Out-Null
            Write-Log "RECYCLED id=$($item.id) original=$($item.original) destination=$($receipt.destination)"
        } catch {
            $failed = $true
            $failure = $_.Exception.Message
            if ($claimed -and -not $confirmed) {
                try { Invoke-Handoff -Arguments @('cancel', '--root', $item.root, '--id', $item.id) | Out-Null }
                catch { Write-Log "CANCEL_FAILED id=$($item.id) $($_.Exception.Message)" }
            }
            Write-Log "FAILED id=$($item.id) original=$($item.original) $failure"
        }
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
if ($failed) { exit 1 }
