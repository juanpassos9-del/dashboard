param(
    [int]$IntervalSeconds = 30,
    [string]$StartTime = "09:00",
    [string]$EndTime = "17:00"
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot ".tmp"
$LogPath = Join-Path $LogDir "regime_juros_sync.log"
$ScriptPath = Join-Path $ProjectRoot "execution\sync_regime_juros.py"

if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-Log {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$stamp | $Message" | Tee-Object -FilePath $LogPath -Append
}

function Test-BusinessWindow {
    $now = Get-Date
    $dayName = $now.DayOfWeek.ToString()
    if ($dayName -in @("Saturday", "Sunday")) {
        return $false
    }

    $start = [datetime]::ParseExact($StartTime, "HH:mm", $null)
    $end = [datetime]::ParseExact($EndTime, "HH:mm", $null)
    $startToday = Get-Date -Hour $start.Hour -Minute $start.Minute -Second 0
    $endToday = Get-Date -Hour $end.Hour -Minute $end.Minute -Second 0

    return ($now -ge $startToday -and $now -lt $endToday)
}

function Wait-ForBusinessWindow {
    $now = Get-Date
    $dayName = $now.DayOfWeek.ToString()
    if ($dayName -in @("Saturday", "Sunday")) {
        return $false
    }

    $start = [datetime]::ParseExact($StartTime, "HH:mm", $null)
    $end = [datetime]::ParseExact($EndTime, "HH:mm", $null)
    $startToday = Get-Date -Hour $start.Hour -Minute $start.Minute -Second 0
    $endToday = Get-Date -Hour $end.Hour -Minute $end.Minute -Second 0

    if ($now -lt $startToday) {
        $waitSeconds = [int]($startToday - $now).TotalSeconds
        if ($waitSeconds -le 180) {
            Write-Log "Aguardando abertura da janela por ${waitSeconds}s."
            Start-Sleep -Seconds ([Math]::Max(1, $waitSeconds + 2))
            return (Test-BusinessWindow)
        }
        return $false
    }

    return ($now -lt $endToday)
}

Set-Location $ProjectRoot
Write-Log "Iniciando sync Regime de Juros. Janela: $StartTime-$EndTime | Intervalo: ${IntervalSeconds}s"

if (!(Wait-ForBusinessWindow)) {
    Write-Log "Fora da janela operacional. Encerrando sync."
    exit 0
}

while (Test-BusinessWindow) {
    try {
        $output = & python $ScriptPath 2>&1
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {
            Write-Log "OK | $($output -join ' ')"
        } else {
            Write-Log "ERRO exit=$exitCode | $($output -join ' ')"
        }
    } catch {
        Write-Log "EXCEPTION | $($_.Exception.Message)"
    }

    Start-Sleep -Seconds $IntervalSeconds
}

Write-Log "Fora da janela operacional. Encerrando sync."
