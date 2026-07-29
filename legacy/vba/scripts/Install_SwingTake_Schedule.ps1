[CmdletBinding()]
param(
    [string]$TaskName = 'VisualBaseball_SwingTake_Daily_Update'
)

$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'Run_SwingTake_Update.ps1'
$workbook = Join-Path (Split-Path $PSScriptRoot -Parent) 'workbooks\visualbaseball_savant_2026_incremental.xlsm'

if (-not (Test-Path -LiteralPath $runner)) { throw "Runner script not found: $runner" }
if (-not (Test-Path -LiteralPath $workbook)) { throw "Workbook not found: $workbook" }

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -WorkbookPath `"$workbook`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At '12:00 PM'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15) -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Daily Visual Baseball incremental workbook update at local noon.' -Force | Out-Null

Write-Host "Registered task: $TaskName"
Write-Host 'Daily trigger: 12:00 PM in the current local Windows timezone.'
Write-Host 'The user must be logged on, Excel desktop must be installed, and the workbook location must remain unchanged.'
