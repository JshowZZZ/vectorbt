param(
    [string]$ProjectRoot = "E:\Project\vectorbt-master",
    [string]$FreqtradeRoot = "E:\Project\freqtrade",
    [string]$ConfigPath = "",
    [bool]$EnsureLiveSignalProducer = $true,
    [string]$ManifestJson = "",
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

function Get-ManagedProcessInfo {
    param([string]$StatePath)
    if (-not (Test-Path $StatePath)) {
        return $null
    }
    try {
        return Get-Content $StatePath -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Stop-ManagedProcess {
    param([object]$Info)
    if ($null -eq $Info) {
        return
    }
    try {
        $proc = Get-Process -Id ([int]$Info.pid) -ErrorAction Stop
        Stop-Process -Id $proc.Id -Force
    }
    catch {
    }
}

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$resolvedFreqtradeRoot = (Resolve-Path $FreqtradeRoot).Path
$resolvedConfigPath = if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    Join-Path $resolvedFreqtradeRoot "user_data\config_autowfo_dryrun.json"
}
else {
    (Resolve-Path $ConfigPath).Path
}

if ($EnsureLiveSignalProducer) {
    $producerScript = Join-Path $resolvedProjectRoot "scripts\start_live_signal_producer.ps1"
    if (-not (Test-Path $producerScript)) {
        throw "live signal producer start script not found: $producerScript"
    }
    $producerArgs = @{
        ProjectRoot = $resolvedProjectRoot
    }
    if ([string]::IsNullOrWhiteSpace($ManifestJson) -eq $false) {
        $producerArgs["ManifestJson"] = $ManifestJson
    }
    if ($ForceRestart.IsPresent) {
        $producerArgs["ForceRestart"] = $true
    }
    & $producerScript @producerArgs | Out-Host
}

$runtimeDir = Join-Path $resolvedProjectRoot "artifacts\paper_dryrun\runtime"
$logsDir = Join-Path $resolvedProjectRoot "artifacts\paper_dryrun\logs"
$null = New-Item -ItemType Directory -Force -Path $runtimeDir, $logsDir

$statePath = Join-Path $runtimeDir "freqtrade_dryrun.json"
$stdoutLog = Join-Path $logsDir "freqtrade_dryrun.stdout.log"
$stderrLog = Join-Path $logsDir "freqtrade_dryrun.stderr.log"

$existing = Get-ManagedProcessInfo -StatePath $statePath
if ($null -ne $existing) {
    $isRunning = $false
    try {
        $proc = Get-Process -Id ([int]$existing.pid) -ErrorAction Stop
        $isRunning = $true
    }
    catch {
        $isRunning = $false
    }
    if ($isRunning -and -not $ForceRestart.IsPresent) {
        Write-Output "freqtrade dry-run already running pid=$($existing.pid)"
        Write-Output "config_path=$($existing.config_path)"
        exit 0
    }
    if ($isRunning -and $ForceRestart.IsPresent) {
        Stop-ManagedProcess -Info $existing
        Start-Sleep -Milliseconds 500
    }
}

$freqtradeExe = Join-Path $resolvedFreqtradeRoot ".venv\Scripts\freqtrade.exe"
$arguments = @(
    "trade",
    "--config",
    $resolvedConfigPath
)

$process = Start-Process -FilePath $freqtradeExe -ArgumentList $arguments -WorkingDirectory $resolvedFreqtradeRoot -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru

$state = [ordered]@{
    component = "freqtrade_dryrun"
    pid = $process.Id
    started_utc = [DateTime]::UtcNow.ToString("o")
    project_root = $resolvedProjectRoot
    freqtrade_root = $resolvedFreqtradeRoot
    config_path = $resolvedConfigPath
    stdout_log = $stdoutLog
    stderr_log = $stderrLog
}
$state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8

Write-Output "started freqtrade dry-run pid=$($process.Id)"
Write-Output "state_path=$statePath"
Write-Output "stdout_log=$stdoutLog"
