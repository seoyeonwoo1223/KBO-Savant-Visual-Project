Attribute VB_Name = "modLogger"
Option Explicit

Public Function NewRunLog(ByVal runId As String) As Object
    Dim row As Object
    Set row = NewDictionary()
    row("run_id") = runId
    row("started_at") = IsoNow()
    row("finished_at") = ""
    row("status") = "RUNNING"
    row("dates_checked") = 0
    row("games_found") = 0
    row("games_downloaded") = 0
    row("games_cached") = 0
    row("games_skipped") = 0
    row("events_added") = 0
    row("pitches_added") = 0
    row("unknown_events") = 0
    row("validation_failures") = 0
    row("error_message") = ""
    Set NewRunLog = row
End Function

Public Sub WriteRunLog(ByVal logRow As Object)
    Dim rows As New Collection
    logRow("finished_at") = IsoNow()
    rows.Add logRow
    AppendDictionaryRows "Update_Log", rows
End Sub

