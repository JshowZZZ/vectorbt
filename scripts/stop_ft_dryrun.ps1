param(
    [string]$ProjectRoot = "E:\Project\vectorbt-master",
    [switch]$StopLiveSignalProducer
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$statePath = Join-Path $resolvedProjectRoot "artifacts\paper_dryrun\runtime\freqtrade_dryrun.json"

if (Test-Path $statePath) {
    $state = Get-Content $statePath -Raw | ConvertFrom-Json
    $stopped = $false
    try {
        $proc = Get-Process -Id ([int]$state.pid) -ErrorAction Stop
        Stop-Process -Id $proc.Id -Force
        $stopped = $true
    }
    catch {
        $stopped = $false
    }
    Remove-Item $statePath -Force -ErrorAction SilentlyContinue
    if ($stopped) {
        Write-Output "stopped freqtrade dry-run pid=$($state.pid)"
    }
    else {
        Write-Output "freqtrade dry-run was not running; removed stale state file"
    }
}
else {
    Write-Output "freqtrade dry-run state file not found"
}

if ($StopLiveSignalProducer.IsPresent) {
    $producerStopScript = Join-Path $resolvedProjectRoot "scripts\stop_live_signal_producer.ps1"
    if (Test-Path $producerStopScript) {
        & $producerStopScript -ProjectRoot $resolvedProjectRoot | Out-Host
    }
}
