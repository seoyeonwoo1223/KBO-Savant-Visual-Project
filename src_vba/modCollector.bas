Attribute VB_Name = "modCollector"
Option Explicit

Public Sub RunCollection(ByVal logRow As Object)
    Dim season As Long, rawSchedule As String, root As Object, schedule As Object
    Dim existing As Object, candidates As New Collection, dateKey As Variant, games As Object, game As Object
    Dim testIds As String, maxGames As Long, gameId As String, statusText As String
    Dim rawGame As String, gameRow As Object, eventRows As Collection, pitchRows As Collection
    Dim unknownCount As Long, sourceLimited As Boolean, validationMessage As String, valid As Boolean
    Dim downloaded As Long, cached As Long, skipped As Long, failures As Long, totalFound As Long
    Dim eventsAdded As Long, pitchesAdded As Long

    season = SafeLong(GetConfigValue("Season", 2026), 2026)
    rawSchedule = HttpGetJson("/api/schedule/season?y=" & season, "/schedule")
    Set root = JsonConverter.ParseJson(rawSchedule)
    Set schedule = JsonObject(root, "schedule")
    If schedule Is Nothing Then Err.Raise vbObjectError + 2401, "RunCollection", "Schedule response did not contain schedule."
    logRow("dates_checked") = schedule.Count
    Set existing = ExistingGamesIndex()
    testIds = SafeText(GetConfigValue("TestGameIds", ""))
    maxGames = SafeLong(GetConfigValue("MaxGamesPerRun", 10), 10)

    For Each dateKey In schedule.Keys
        Set games = schedule(dateKey)
        For Each game In games
            gameId = JsonText(game, "gameId")
            statusText = JsonText(game, "status")
            If Len(testIds) > 0 And Not CsvContains(testIds, gameId) Then GoTo NextGame
            If Not IsFinalStatus(statusText) Then
                skipped = skipped + 1
                GoTo NextGame
            End If
            totalFound = totalFound + 1
            If IsFullyCachedGame(existing, gameId, CStr(dateKey)) Then
                skipped = skipped + 1
            ElseIf maxGames <= 0 Or candidates.Count < maxGames Then
                candidates.Add game
            End If
NextGame:
        Next game
    Next dateKey

    logRow("games_found") = totalFound
    For Each game In candidates
        gameId = JsonText(game, "gameId")
        unknownCount = 0
        sourceLimited = False
        On Error GoTo GameFailed
        rawGame = HttpGetJson("/api/game/pbp?id=" & gameId, "/game/" & gameId & "/pbp")
        downloaded = downloaded + 1
        SavePendingRaw gameId, rawGame
        ParseGameResponse rawGame, game, gameRow, eventRows, pitchRows, unknownCount, sourceLimited
        valid = ValidateParsedGame(gameRow, eventRows, pitchRows, validationMessage)
        If valid And CBool(gameRow("is_final")) Then
            DeleteGameRows "Events", gameId
            DeleteGameRows "Pitches", gameId
            AppendDictionaryRows "Events", eventRows
            AppendDictionaryRows "Pitches", pitchRows
            PromotePendingRaw gameId
            gameRow("raw_cache_path") = RawGamePath(gameId)
            gameRow("source_hash") = ComputeFileHash(RawGamePath(gameId))
            gameRow("validation_status") = "PASS"
            UpsertGameRow gameRow
            cached = cached + 1
            eventsAdded = eventsAdded + eventRows.Count
            pitchesAdded = pitchesAdded + pitchRows.Count
        Else
            gameRow("source_hash") = ComputeFileHash(PendingGamePath(gameId))
            gameRow("validation_status") = "FAIL: " & validationMessage
            UpsertGameRow gameRow
            failures = failures + 1
        End If
        logRow("unknown_events") = SafeLong(logRow("unknown_events")) + unknownCount
        On Error GoTo 0
        GoTo ContinueGame
GameFailed:
        failures = failures + 1
        logRow("error_message") = Left$(SafeText(logRow("error_message")) & IIf(Len(SafeText(logRow("error_message"))) > 0, " | ", "") & gameId & ": " & Err.Description, 32000)
        Err.Clear
        On Error GoTo 0
ContinueGame:
    Next game

    logRow("games_downloaded") = downloaded
    logRow("games_cached") = cached
    logRow("games_skipped") = skipped
    logRow("events_added") = eventsAdded
    logRow("pitches_added") = pitchesAdded
    logRow("validation_failures") = failures
    If failures > 0 Then logRow("status") = "PARTIAL" Else logRow("status") = "SUCCESS"
End Sub

Private Function IsFullyCachedGame(ByVal existing As Object, ByVal gameId As String, ByVal gameDate As String) As Boolean
    Dim row As Object, recheckDays As Long
    If Not existing.Exists(gameId) Then Exit Function
    Set row = existing(gameId)
    If Not CBool(row("is_final")) Then Exit Function
    If SafeText(row("validation_status")) <> "PASS" Then Exit Function
    If Not RawGameExists(gameId) Then Exit Function
    recheckDays = SafeLong(GetConfigValue("RecheckRecentDays", 2), 2)
    If recheckDays > 0 Then
        On Error Resume Next
        If DateDiff("d", CDate(gameDate), Date) <= recheckDays Then
            On Error GoTo 0
            Exit Function
        End If
        On Error GoTo 0
    End If
    IsFullyCachedGame = True
End Function

