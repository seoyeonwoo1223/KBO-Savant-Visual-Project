Attribute VB_Name = "modExcelWriter"
Option Explicit

Public Sub EnsureWorkbookStructure()
    Dim ws As Worksheet
    EnsureConfigDefaults

    Set ws = GetOrCreateSheet("Games")
    EnsureHeaders ws, Split("season,game_date,game_id,away_team,home_team,stadium,game_status,away_score,home_score,is_final,fetched_at,source_url,raw_cache_path,source_hash,validation_status", ",")

    Set ws = GetOrCreateSheet("Events")
    EnsureHeaders ws, Split("game_id,event_seq,inning,inning_half,pa_id,event_type,event_code,description,batter_id,batter_name,pitcher_id,pitcher_name,runner_id,runner_name,from_base,to_base,is_out,is_run,outs_before,outs_after,base_state_before,base_state_after,runs_on_event,away_score_before,home_score_before,away_score_after,home_score_after,parse_status", ",")

    Set ws = GetOrCreateSheet("Pitches")
    EnsureHeaders ws, Split("season,game_date,game_id,event_seq,pa_id,pitch_id,pitch_number,inning,inning_half,batter_id,batter_name,pitcher_id,pitcher_name", ",")
    EnsureHeaders ws, Split("balls_before,strikes_before,outs_before,runner_on_1b_before,runner_on_2b_before,runner_on_3b_before,base_state_before,away_score_before,home_score_before", ",")
    EnsureHeaders ws, Split("pitch_type,velocity,px,pz,pitch_call_code,pitch_result,pa_result,description,is_swing,is_take,is_contact,is_in_play,is_pa_terminal", ",")
    EnsureHeaders ws, Split("balls_after,strikes_after,outs_after,runner_on_1b_after,runner_on_2b_after,runner_on_3b_after,base_state_after,runs_on_pitch,away_score_after,home_score_after", ",")
    EnsureHeaders ws, Split("base_state_code_before,re24_state_code_before,re288_state_code_before,base_state_code_after,re24_state_code_after,re288_state_code_after,parse_status,fetched_at,source_url", ",")
    EnsureHeaders ws, Split("pitch_type_code,pitch_type_kr,velocity_kmh,velocity_mph,sz_top,sz_bottom,release_height_cm,arrival_time_s,vertical_movement_cm,horizontal_movement_cm,drop_angle,x0,z0,vx0,vy0,vz0,ax,ay,az", ",")

    Set ws = GetOrCreateSheet("Update_Log")
    EnsureHeaders ws, Split("run_id,started_at,finished_at,status,dates_checked,games_found,games_downloaded,games_cached,games_skipped,events_added,pitches_added,unknown_events,validation_failures,error_message", ",")

    FormatDataSheet ThisWorkbook.Worksheets("Config"), "Config"
    FormatDataSheet ThisWorkbook.Worksheets("Games"), "Games"
    FormatDataSheet ThisWorkbook.Worksheets("Events"), "Events"
    FormatDataSheet ThisWorkbook.Worksheets("Pitches"), "Pitches"
    FormatDataSheet ThisWorkbook.Worksheets("Update_Log"), "Update_Log"
End Sub

Public Sub EnsureHeaders(ByVal ws As Worksheet, ByVal headers As Variant)
    Dim map As Object, item As Variant, nextCol As Long
    Set map = HeaderMap(ws)
    nextCol = LastHeaderColumn(ws) + 1
    If nextCol < 1 Then nextCol = 1
    For Each item In headers
        If Not map.Exists(CStr(item)) Then
            ws.Cells(1, nextCol).Value = CStr(item)
            map(CStr(item)) = nextCol
            nextCol = nextCol + 1
        End If
    Next item
End Sub

Public Function HeaderMap(ByVal ws As Worksheet) As Object
    Dim result As Object, lastCol As Long, col As Long, header As String
    Set result = NewDictionary()
    lastCol = LastHeaderColumn(ws)
    For col = 1 To lastCol
        header = SafeText(ws.Cells(1, col).Value2)
        If Len(header) > 0 Then result(header) = col
    Next col
    Set HeaderMap = result
End Function

Private Function LastHeaderColumn(ByVal ws As Worksheet) As Long
    If Application.WorksheetFunction.CountA(ws.Rows(1)) = 0 Then
        LastHeaderColumn = 0
    Else
        LastHeaderColumn = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
    End If
End Function

Public Sub AppendDictionaryRows(ByVal sheetName As String, ByVal rows As Collection)
    Dim ws As Worksheet, headers As Object, data() As Variant
    Dim firstRow As Long, lastCol As Long, r As Long, c As Long, key As String
    If rows Is Nothing Then Exit Sub
    If rows.Count = 0 Then Exit Sub
    Set ws = ThisWorkbook.Worksheets(sheetName)
    Set headers = HeaderMap(ws)
    lastCol = LastHeaderColumn(ws)
    ReDim data(1 To rows.Count, 1 To lastCol)
    For r = 1 To rows.Count
        For c = 1 To lastCol
            key = SafeText(ws.Cells(1, c).Value2)
            If rows(r).Exists(key) Then data(r, c) = rows(r)(key)
        Next c
    Next r
    firstRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row + 1
    If firstRow < 2 Then firstRow = 2
    ws.Cells(firstRow, 1).Resize(rows.Count, lastCol).Value = data
End Sub

Public Sub UpsertGameRow(ByVal gameRow As Object)
    Dim ws As Worksheet, headers As Object, gameCol As Long, found As Variant
    Dim targetRow As Long, key As Variant
    Set ws = ThisWorkbook.Worksheets("Games")
    Set headers = HeaderMap(ws)
    gameCol = headers("game_id")
    found = Application.Match(gameRow("game_id"), ws.Columns(gameCol), 0)
    If IsError(found) Then
        targetRow = ws.Cells(ws.Rows.Count, gameCol).End(xlUp).Row + 1
        If targetRow < 2 Then targetRow = 2
    Else
        targetRow = CLng(found)
    End If
    For Each key In gameRow.Keys
        If headers.Exists(CStr(key)) Then ws.Cells(targetRow, headers(CStr(key))).Value = gameRow(key)
    Next key
End Sub

Public Sub DeleteGameRows(ByVal sheetName As String, ByVal gameId As String)
    Dim ws As Worksheet, headers As Object, gameCol As Long, lastRow As Long, lastCol As Long
    Dim fullRange As Range, visibleRows As Range
    Set ws = ThisWorkbook.Worksheets(sheetName)
    Set headers = HeaderMap(ws)
    If Not headers.Exists("game_id") Then Exit Sub
    gameCol = headers("game_id")
    lastRow = ws.Cells(ws.Rows.Count, gameCol).End(xlUp).Row
    If lastRow < 2 Then Exit Sub
    lastCol = LastHeaderColumn(ws)
    Set fullRange = ws.Range(ws.Cells(1, 1), ws.Cells(lastRow, lastCol))
    fullRange.AutoFilter Field:=gameCol, Criteria1:=gameId
    On Error Resume Next
    Set visibleRows = ws.Range(ws.Cells(2, 1), ws.Cells(lastRow, lastCol)).SpecialCells(xlCellTypeVisible)
    On Error GoTo 0
    If Not visibleRows Is Nothing Then visibleRows.EntireRow.Delete
    If ws.AutoFilterMode Then ws.AutoFilterMode = False
End Sub

Public Function ExistingGamesIndex() As Object
    Dim ws As Worksheet, headers As Object, result As Object, lastRow As Long
    Dim r As Long, item As Object, gameId As String
    Set result = NewDictionary()
    Set ws = ThisWorkbook.Worksheets("Games")
    Set headers = HeaderMap(ws)
    lastRow = ws.Cells(ws.Rows.Count, headers("game_id")).End(xlUp).Row
    For r = 2 To lastRow
        gameId = SafeText(ws.Cells(r, headers("game_id")).Value2)
        If Len(gameId) > 0 Then
            Set item = NewDictionary()
            item("is_final") = CBool(ws.Cells(r, headers("is_final")).Value)
            item("validation_status") = SafeText(ws.Cells(r, headers("validation_status")).Value2)
            item("game_date") = SafeText(ws.Cells(r, headers("game_date")).Text)
            result.Add gameId, item
        End If
    Next r
    Set ExistingGamesIndex = result
End Function

Public Sub FormatDataSheet(ByVal ws As Worksheet, ByVal roleName As String)
    Dim lastCol As Long
    lastCol = LastHeaderColumn(ws)
    If lastCol = 0 Then Exit Sub
    With ws.Range(ws.Cells(1, 1), ws.Cells(1, lastCol))
        .Interior.Color = RGB(31, 78, 121)
        .Font.Color = RGB(255, 255, 255)
        .Font.Bold = True
        .HorizontalAlignment = xlCenter
        .VerticalAlignment = xlCenter
        .WrapText = True
    End With
    ws.Rows(1).RowHeight = 32
    ws.Rows(1).AutoFilter
    ws.Activate
    ActiveWindow.FreezePanes = False
    ws.Range("A2").Select
    ActiveWindow.FreezePanes = True
    If roleName = "Config" Then
        ws.Columns(1).ColumnWidth = 24
        ws.Columns(2).ColumnWidth = 64
    Else
        ws.Range(ws.Columns(1), ws.Columns(lastCol)).ColumnWidth = 14
        ws.Columns(1).ColumnWidth = 18
    End If
End Sub
