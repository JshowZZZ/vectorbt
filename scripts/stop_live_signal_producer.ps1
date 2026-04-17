param(
    [string]$ProjectRoot = "E:\Project\vectorbt-master"
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$statePath = Join-Path $resolvedProjectRoot "artifacts\paper_dryrun\runtime\live_signal_producer.json"

if (-not (Test-Path $statePath)) {
    Write-Output "live signal producer state file not found"
    exit 0
}

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
    Write-Output "stopped live signal producer pid=$($state.pid)"
}
else {
    Write-Output "live signal producer was not running; removed stale state file"
}
