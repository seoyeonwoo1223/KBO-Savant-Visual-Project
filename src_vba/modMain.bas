Attribute VB_Name = "modMain"
Option Explicit

Public Sub InitializeIncrementalWorkbook()
    Dim ws As Worksheet, readme As Worksheet
    Dim oldCalc As XlCalculation
    oldCalc = Application.Calculation
    Application.ScreenUpdating = False
    Application.DisplayAlerts = False
    Application.Calculation = xlCalculationManual
    On Error GoTo CleanFail

    If SheetExists("Savant") And Not SheetExists("Pitches") Then ThisWorkbook.Worksheets("Savant").Name = "Pitches"
    If SheetExists("Pitches") Then
        Set ws = ThisWorkbook.Worksheets("Pitches")
        If SafeText(ws.Cells(1, 12).Value2) = "IVB (in)" And SafeText(ws.Cells(1, 10).Value2) = "Pitch Velo (MPH)" Then ws.Columns(11).Delete
    End If
    EnsureWorkbookStructure
    Set readme = GetOrCreateSheet("README")
    WriteReadmeSheet readme
    ThisWorkbook.Worksheets("Config").Activate
    ThisWorkbook.Save

CleanExit:
    Application.Calculation = oldCalc
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
    Exit Sub
CleanFail:
    Application.Calculation = oldCalc
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
    Err.Raise Err.Number, "InitializeIncrementalWorkbook", Err.Description
End Sub

Public Sub RunIncrementalUpdate()
    Dim logRow As Object, runId As String, errorNumber As Long, errorText As String
    Dim oldCalc As XlCalculation
    oldCalc = Application.Calculation
    Application.ScreenUpdating = False
    Application.DisplayAlerts = False
    Application.EnableEvents = False
    Application.Calculation = xlCalculationManual
    runId = Format$(Now, "yyyymmdd_hhnnss")
    On Error GoTo Failed

    EnsureWorkbookStructure
    AcquireUpdateLock
    Set logRow = NewRunLog(runId)
    ResetHttpSession
    RunCollection logRow
    SetConfigValue "LastSuccessfulRun", IsoNow()
    WriteRunLog logRow
    ThisWorkbook.Save
    GoTo CleanExit

Failed:
    errorNumber = Err.Number
    errorText = Err.Description
    If logRow Is Nothing Then Set logRow = NewRunLog(runId)
    logRow("status") = "FAILED"
    logRow("error_message") = errorText
    On Error Resume Next
    WriteRunLog logRow
    ThisWorkbook.Save
    On Error GoTo 0

CleanExit:
    ReleaseUpdateLock
    Application.Calculation = oldCalc
    Application.EnableEvents = True
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
    If errorNumber <> 0 Then Err.Raise errorNumber, "RunIncrementalUpdate", errorText
End Sub

Private Function SheetExists(ByVal sheetName As String) As Boolean
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets(sheetName)
    SheetExists = Not ws Is Nothing
    On Error GoTo 0
End Function

Private Sub WriteReadmeSheet(ByVal ws As Worksheet)
    Dim rows As Variant, i As Long
    ws.Cells.Clear
    rows = Array( _
        Array("Item", "Value"), _
        Array("Purpose", "Incremental public Visual Baseball schedule and play-by-play collector with state reconstruction."), _
        Array("Entry point", "RunIncrementalUpdate"), _
        Array("Schedule endpoint", "https://visualbaseball.com/api/schedule/season?y=YYYY"), _
        Array("Date endpoint", "https://visualbaseball.com/api/schedule/date?d=YYYY-MM-DD"), _
        Array("Game endpoint", "https://visualbaseball.com/api/game/pbp?id=GAME_ID"), _
        Array("Public session", "Load /schedule, retain returned cookies, read the api-token meta value, and send X-Api-Token on same-origin GET requests."), _
        Array("Base code", "Integer 0-7. First base adds 1, second base adds 2, third base adds 4."), _
        Array("RE24 state code", "base_code * 3 + outs; identifier only, no expectancy value is calculated."), _
        Array("RE288 state code", "((RE24_state * 4 + balls) * 3 + strikes); identifier only."), _
        Array("Pitch codes", "B=ball, F=foul, S=swinging strike, T=called strike, X=ball in play."), _
        Array("Cache", "cache\raw\<season>\<game_id>.json after official-final validation; pending files remain retryable."), _
        Array("Incremental keys", "Games: game_id; Events: game_id + event_seq; Pitches: pitch_id or game_id + pa_id + pitch_number."), _
        Array("Source limitation", "The public response exposes pitches, plate-appearance results, substitutions, and PA-boundary base snapshots. It does not expose every non-pitch runner action as an original coded event."), _
        Array("Unknown handling", "Unexposed snapshot changes and unknown codes are retained with parse_status=unknown and are never silently discarded."), _
        Array("Validation", "Final score, event order, pitch keys, legal counts/outs, PA resets, half-inning resets, and two-strike fouls."), _
        Array("Excluded work", "No expectancy values, run values, zone classifications, leaderboards, dashboards, or models are calculated."), _
        Array("JSON parser", "VBA-JSON v2.3.1 by Tim Hall, MIT license: https://github.com/VBA-tools/VBA-JSON"))
    For i = LBound(rows) To UBound(rows)
        ws.Cells(i + 1, 1).Value = rows(i)(0)
        ws.Cells(i + 1, 2).Value = rows(i)(1)
    Next i
    ws.Range("A1:B1").Interior.Color = RGB(31, 78, 121)
    ws.Range("A1:B1").Font.Color = RGB(255, 255, 255)
    ws.Range("A1:B1").Font.Bold = True
    ws.Columns(1).ColumnWidth = 24
    ws.Columns(2).ColumnWidth = 110
    ws.Columns(2).WrapText = True
    ws.UsedRange.Rows.AutoFit
End Sub
