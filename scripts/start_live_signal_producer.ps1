param(
    [string]$ProjectRoot = "E:\Project\vectorbt-master",
    [string]$ManifestJson = "",
    [int]$IntervalSeconds = 900,
    [string]$PythonExe = "",
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

function Resolve-BundleManifest {
    param([string]$ProjectRootPath, [string]$ExplicitManifest)
    if ([string]::IsNullOrWhiteSpace($ExplicitManifest) -eq $false) {
        return (Resolve-Path $ExplicitManifest).Path
    }
    $bridgeRoot = Join-Path $ProjectRootPath "artifacts\freqtrade_bridge"
    if (-not (Test-Path $bridgeRoot)) {
        throw "bridge bundle root not found: $bridgeRoot"
    }
    $candidate = Get-ChildItem $bridgeRoot -Recurse -Filter signal_manifest.json |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $candidate) {
        throw "no signal_manifest.json found under $bridgeRoot"
    }
    return $candidate.FullName
}

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$resolvedManifest = Resolve-BundleManifest -ProjectRootPath $resolvedProjectRoot -ExplicitManifest $ManifestJson
$resolvedPythonExe = if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    Join-Path $resolvedProjectRoot ".venv\Scripts\python.exe"
}
else {
    (Resolve-Path $PythonExe).Path
}

$runtimeDir = Join-Path $resolvedProjectRoot "artifacts\paper_dryrun\runtime"
$logsDir = Join-Path $resolvedProjectRoot "artifacts\paper_dryrun\logs"
$null = New-Item -ItemType Directory -Force -Path $runtimeDir, $logsDir

$statePath = Join-Path $runtimeDir "live_signal_producer.json"
$stdoutLog = Join-Path $logsDir "live_signal_producer.stdout.log"
$stderrLog = Join-Path $logsDir "live_signal_producer.stderr.log"

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
        Write-Output "live signal producer already running pid=$($existing.pid)"
        Write-Output "manifest_json=$($existing.manifest_json)"
        exit 0
    }
    if ($isRunning -and $ForceRestart.IsPresent) {
        Stop-ManagedProcess -Info $existing
        Start-Sleep -Milliseconds 500
    }
}

$arguments = @(
    "-u",
    "-m",
    "autowfo",
    "bridge-live-signal",
    "--manifest-json",
    $resolvedManifest,
    "--interval",
    [string]$IntervalSeconds,
    "--cwd",
    $resolvedProjectRoot
)

$process = Start-Process -FilePath $resolvedPythonExe -ArgumentList $arguments -WorkingDirectory $resolvedProjectRoot -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru

$state = [ordered]@{
    component = "live_signal_producer"
    pid = $process.Id
    started_utc = [DateTime]::UtcNow.ToString("o")
    project_root = $resolvedProjectRoot
    manifest_json = $resolvedManifest
    interval_seconds = $IntervalSeconds
    python_exe = $resolvedPythonExe
    stdout_log = $stdoutLog
    stderr_log = $stderrLog
}
$state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8

Write-Output "started live signal producer pid=$($process.Id)"
Write-Output "state_path=$statePath"
Write-Output "stdout_log=$stdoutLog"
