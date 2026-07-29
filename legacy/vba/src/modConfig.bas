Attribute VB_Name = "modConfig"
Option Explicit

Public Sub EnsureConfigDefaults()
    Dim ws As Worksheet
    Set ws = GetOrCreateSheet("Config")
    If SafeText(ws.Cells(1, 1).Value2) = "" Then
        ws.Cells(1, 1).Value = "Setting"
        ws.Cells(1, 2).Value = "Value"
    End If
    SetConfigDefault "Season", 2026
    SetConfigDefault "BaseURL", "https://visualbaseball.com"
    SetConfigDefault "CacheFolder", JoinPath(ThisWorkbook.Path, "cache")
    SetConfigDefault "LastSuccessfulRun", ""
    SetConfigDefault "RequestIntervalMs", 1000
    SetConfigDefault "MaxRetries", 3
    SetConfigDefault "RecheckRecentDays", 2
    SetConfigDefault "Timezone", "Asia/Seoul"
    SetConfigDefault "MaxGamesPerRun", 10
    SetConfigDefault "TestGameIds", ""
End Sub

Private Sub SetConfigDefault(ByVal settingName As String, ByVal defaultValue As Variant)
    Dim ws As Worksheet, rowNumber As Long
    Set ws = ThisWorkbook.Worksheets("Config")
    rowNumber = FindConfigRow(settingName)
    If rowNumber = 0 Then
        rowNumber = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row + 1
        ws.Cells(rowNumber, 1).Value = settingName
        ws.Cells(rowNumber, 2).Value = defaultValue
    End If
End Sub

Public Function GetConfigValue(ByVal settingName As String, Optional ByVal fallback As Variant) As Variant
    Dim rowNumber As Long
    rowNumber = FindConfigRow(settingName)
    If rowNumber = 0 Then
        GetConfigValue = fallback
    Else
        GetConfigValue = ThisWorkbook.Worksheets("Config").Cells(rowNumber, 2).Value2
        If IsEmpty(GetConfigValue) Then GetConfigValue = fallback
    End If
End Function

Public Sub SetConfigValue(ByVal settingName As String, ByVal value As Variant)
    Dim ws As Worksheet, rowNumber As Long
    Set ws = ThisWorkbook.Worksheets("Config")
    rowNumber = FindConfigRow(settingName)
    If rowNumber = 0 Then
        rowNumber = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row + 1
        ws.Cells(rowNumber, 1).Value = settingName
    End If
    ws.Cells(rowNumber, 2).Value = value
End Sub

Private Function FindConfigRow(ByVal settingName As String) As Long
    Dim ws As Worksheet, lastRow As Long, i As Long
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets("Config")
    On Error GoTo 0
    If ws Is Nothing Then Exit Function
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    For i = 2 To lastRow
        If StrComp(SafeText(ws.Cells(i, 1).Value2), settingName, vbTextCompare) = 0 Then
            FindConfigRow = i
            Exit Function
        End If
    Next i
End Function

Public Function CacheFolderPath() As String
    CacheFolderPath = SafeText(GetConfigValue("CacheFolder", JoinPath(ThisWorkbook.Path, "cache")))
End Function

Public Function GetOrCreateSheet(ByVal sheetName As String) As Worksheet
    On Error Resume Next
    Set GetOrCreateSheet = ThisWorkbook.Worksheets(sheetName)
    On Error GoTo 0
    If GetOrCreateSheet Is Nothing Then
        Set GetOrCreateSheet = ThisWorkbook.Worksheets.Add(After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count))
        GetOrCreateSheet.Name = sheetName
    End If
End Function

