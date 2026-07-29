[CmdletBinding()]
param(
    [string]$WorkbookPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'workbooks\visualbaseball_savant_2026_incremental.xlsm')
)

$ErrorActionPreference = 'Stop'
$excel = $null
$workbook = $null
$exitCode = 1

try {
    $resolved = (Resolve-Path -LiteralPath $WorkbookPath).Path
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AutomationSecurity = 1
    $workbook = $excel.Workbooks.Open($resolved, 0, $false)
    $macro = "'$($workbook.Name)'!RunIncrementalUpdate"
    $excel.Run($macro)
    $workbook.Save()
    $exitCode = 0
    Write-Host "Visual Baseball update completed: $resolved"
}
catch {
    Write-Error "Visual Baseball update failed: $($_.Exception.Message)"
    $exitCode = 1
}
finally {
    if ($workbook) {
        try { $workbook.Close($true) } catch { }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($workbook)
    }
    if ($excel) {
        try { $excel.Quit() } catch { }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

exit $exitCode
