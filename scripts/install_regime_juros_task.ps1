param(
    [string]$TaskName = "TTS Regime Juros Sync",
    [string]$StartTime = "09:00",
    [string]$EndTime = "17:00",
    [int]$IntervalSeconds = 30
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LoopScript = Join-Path $ProjectRoot "scripts\sync_regime_juros_loop.ps1"

if (!(Test-Path $LoopScript)) {
    throw "Script de loop nao encontrado: $LoopScript"
}

$start = [datetime]::ParseExact($StartTime, "HH:mm", $null)
$end = [datetime]::ParseExact($EndTime, "HH:mm", $null)
$duration = $end - $start
if ($duration.TotalMinutes -le 0) {
    throw "EndTime precisa ser maior que StartTime."
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$LoopScript`"",
    "-IntervalSeconds", $IntervalSeconds,
    "-StartTime", "`"$StartTime`"",
    "-EndTime", "`"$EndTime`""
) -join " "

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $args -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $start
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ($duration.Add([TimeSpan]::FromMinutes(15))
)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null

Write-Host "Tarefa criada/atualizada: $TaskName"
Write-Host "Agenda: segunda a sexta, $StartTime-$EndTime, intervalo interno ${IntervalSeconds}s"
Write-Host "Log: $ProjectRoot\.tmp\regime_juros_sync.log"
Write-Host "Para testar agora: Start-ScheduledTask -TaskName `"$TaskName`""
