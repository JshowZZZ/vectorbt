param(
    [string]$ProjectRoot = "E:\Project\vectorbt-master",
    [int]$TailLines = 20
)

$ErrorActionPreference = "Stop"

function Get-ManagedStatus {
    param([string]$StatePath, [string]$Name)
    if (-not (Test-Path $StatePath)) {
        return [pscustomobject]@{
            Name = $Name
            Running = $false
            Pid = $null
            StartedUtc = $null
            StdoutLog = $null
            StderrLog = $null
        }
    }
    $state = Get-Content $StatePath -Raw | ConvertFrom-Json
    $running = $false
    try {
        $null = Get-Process -Id ([int]$state.pid) -ErrorAction Stop
        $running = $true
    }
    catch {
        $running = $false
    }
    return [pscustomobject]@{
        Name = $Name
        Running = $running
        Pid = $state.pid
        StartedUtc = $state.started_utc
        StdoutLog = $state.stdout_log
        StderrLog = $state.stderr_log
    }
}

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$runtimeDir = Join-Path $resolvedProjectRoot "artifacts\paper_dryrun\runtime"
$liveStatePath = Join-Path $runtimeDir "live_signal_producer.json"
$ftStatePath = Join-Path $runtimeDir "freqtrade_dryrun.json"

$statuses = @()
$statuses += Get-ManagedStatus -StatePath $liveStatePath -Name "live_signal_producer"
$statuses += Get-ManagedStatus -StatePath $ftStatePath -Name "freqtrade_dryrun"

$statuses | Format-Table -AutoSize Name, Running, Pid, StartedUtc

$liveManifestPath = Join-Path $resolvedProjectRoot "artifacts\live_signal_store\live_manifest.json"
if (Test-Path $liveManifestPath) {
    try {
        $manifest = Get-Content $liveManifestPath -Raw | ConvertFrom-Json
        Write-Output "live manifest last_bar_utc=$($manifest.signals.last_bar_utc)"
        Write-Output "live manifest rows=$($manifest.signals.rows) pairs=$($manifest.signals.pairs.Count)"
    }
    catch {
        Write-Output "live manifest unreadable: $($_.Exception.Message)"
    }
}

foreach ($status in $statuses) {
    if ([string]::IsNullOrWhiteSpace($status.StdoutLog)) {
        continue
    }
    if (-not (Test-Path $status.StdoutLog)) {
        continue
    }
    Write-Output "--- $($status.Name) stdout tail ---"
    Get-Content $status.StdoutLog -Tail ([Math]::Max($TailLines, 1))
    if ([string]::IsNullOrWhiteSpace($status.StderrLog) -eq $false -and (Test-Path $status.StderrLog)) {
        $stderrLines = Get-Content $status.StderrLog -Tail ([Math]::Max($TailLines, 1))
        if ($stderrLines.Count -gt 0) {
            Write-Output "--- $($status.Name) stderr tail ---"
            $stderrLines
        }
    }
}