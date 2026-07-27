Attribute VB_Name = "modValidation"
Option Explicit

Public Function ValidateParsedGame(ByVal gameRow As Object, ByVal events As Collection, ByVal pitches As Collection, ByRef validationMessage As String) As Boolean
    Dim eventKeys As Object, pitchKeys As Object, row As Object, key As String
    Dim lastPitch As Object, lastEvent As Object, firstByHalf As Object, paFirst As Object
    Dim halfKey As String, paId As String
    Set eventKeys = NewDictionary()
    Set pitchKeys = NewDictionary()
    Set firstByHalf = NewDictionary()
    Set paFirst = NewDictionary()

    For Each row In events
        key = CStr(row("event_seq"))
        If eventKeys.Exists(key) Then validationMessage = "Duplicate event sequence: " & key: Exit Function
        eventKeys(key) = True
        Set lastEvent = row
    Next row

    For Each row In pitches
        key = SafeText(row("pitch_id"))
        If pitchKeys.Exists(key) Then validationMessage = "Duplicate pitch key: " & key: Exit Function
        pitchKeys(key) = True
        If SafeLong(row("balls_before"), -1) < 0 Or SafeLong(row("balls_before"), -1) > 3 Then validationMessage = "Invalid balls_before": Exit Function
        If SafeLong(row("strikes_before"), -1) < 0 Or SafeLong(row("strikes_before"), -1) > 2 Then validationMessage = "Invalid strikes_before": Exit Function
        If SafeLong(row("outs_before"), -1) < 0 Or SafeLong(row("outs_before"), -1) > 2 Then validationMessage = "Invalid outs_before": Exit Function
        If SafeLong(row("outs_after"), -1) < 0 Or SafeLong(row("outs_after"), -1) > 3 Then validationMessage = "Invalid outs_after": Exit Function
        paId = SafeText(row("pa_id"))
        If Not paFirst.Exists(paId) Then
            paFirst(paId) = True
            If SafeLong(row("balls_before")) <> 0 Or SafeLong(row("strikes_before")) <> 0 Then validationMessage = "Plate appearance did not begin at 0-0": Exit Function
        End If
        If SafeText(row("pitch_call_code")) = "F" And SafeLong(row("strikes_before")) = 2 Then
            If SafeLong(row("strikes_after")) <> 2 And Not CBool(row("is_pa_terminal")) Then validationMessage = "Two-strike foul changed the strike count": Exit Function
        End If
        halfKey = CStr(row("inning")) & "|" & SafeText(row("inning_half"))
        If Not firstByHalf.Exists(halfKey) Then
            firstByHalf(halfKey) = True
            If SafeLong(row("outs_before")) <> 0 Or SafeLong(row("base_state_code_before")) <> 0 Then validationMessage = "Half-inning did not begin empty with zero outs": Exit Function
        End If
        Set lastPitch = row
    Next row

    If lastPitch Is Nothing Then validationMessage = "No pitches were parsed": Exit Function
    If lastEvent Is Nothing Then validationMessage = "No events were parsed": Exit Function
    If SafeLong(lastEvent("away_score_after"), -1) <> SafeLong(gameRow("away_score"), -2) Or _
       SafeLong(lastEvent("home_score_after"), -1) <> SafeLong(gameRow("home_score"), -2) Then
        validationMessage = "Reconstructed final score did not match the official score"
        Exit Function
    End If
    ValidateParsedGame = True
    validationMessage = "PASS"
End Function
