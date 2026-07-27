Attribute VB_Name = "modParser"
Option Explicit

Public Sub ParseGameResponse(ByVal jsonPayload As String, ByVal scheduleGame As Object, ByRef gameRow As Object, ByRef events As Collection, ByRef pitches As Collection, ByRef unknownCount As Long, ByRef sourceLimited As Boolean)
    Dim root As Object, gameData As Object, halves As Object, half As Object
    Dim pa As Object, paList As Object, pitchList As Object, pitch As Object
    Dim basesBefore As Object, basesAfter As Object, subs As Object, subItem As Object
    Dim state As Object, beforeState As Object, afterState As Object, terminalBefore As Object
    Dim eventSeq As Long, paCounter As Long, gamePitchCounter As Long, pitchNumber As Long
    Dim inning As Long, inningHalf As String, paId As String, i As Long, runsOnPlay As Long
    Dim outsAfter As Long, fetchedAt As String, sourceUrl As String, scoreAfter As Object
    Dim officialAway As Long, officialHome As Long, paStatus As String, scoreRuns As Long
    Dim hadPitches As Boolean

    Set root = JsonConverter.ParseJson(jsonPayload)
    Set gameData = JsonObject(root, "gameData")
    Set halves = JsonObject(root, "pbpData")
    If gameData Is Nothing Or halves Is Nothing Then Err.Raise vbObjectError + 2301, "ParseGameResponse", "Required gameData/pbpData fields were missing."

    Set events = New Collection
    Set pitches = New Collection
    Set gameRow = BuildGameRow(gameData, scheduleGame)
    Set state = NewGameState()
    fetchedAt = SafeText(gameRow("fetched_at"))
    sourceUrl = SafeText(gameRow("source_url"))

    For Each half In halves
        inning = JsonLong(half, "inning")
        inningHalf = JsonText(half, "half")
        BeginHalfInning state, inning, inningHalf
        Set paList = JsonObject(half, "pas")
        If paList Is Nothing Then GoTo NextHalf

        For Each pa In paList
            paCounter = paCounter + 1
            paId = SafeText(gameRow("game_id")) & "-" & Format$(paCounter, "000")
            state("current_pa_id") = paId
            state("balls") = 0
            state("strikes") = 0
            Set basesBefore = JsonObject(pa, "basesBefore")
            Set basesAfter = JsonObject(pa, "basesAfter")

            If Not basesBefore Is Nothing Then
                If Not BasesMatchJson(state, basesBefore) Then
                    Set beforeState = CloneState(state)
                    SetBasesFromJson state, basesBefore
                    Set afterState = CloneState(state)
                    eventSeq = eventSeq + 1
                    events.Add MakeEventRow(gameRow, eventSeq, paId, "state_adjustment", "SOURCE_SNAPSHOT", _
                        "Source base snapshot changed; the underlying non-pitch event was not exposed.", pa, beforeState, afterState, 0, "unknown")
                    unknownCount = unknownCount + 1
                    sourceLimited = True
                End If
            End If

            Set subs = JsonObject(pa, "subs")
            If Not subs Is Nothing Then
                For Each subItem In subs
                    eventSeq = eventSeq + 1
                    events.Add MakeSubstitutionEvent(gameRow, eventSeq, paId, pa, subItem, state)
                Next subItem
            End If

            outsAfter = JsonLong(pa, "outsAfter", SafeLong(state("outs")))
            paStatus = PaParseStatus(JsonText(pa, "type"))
            If paStatus = "unknown" Then unknownCount = unknownCount + 1
            Set pitchList = JsonObject(pa, "pitches")
            pitchNumber = 0
            hadPitches = False
            Set terminalBefore = Nothing

            If Not pitchList Is Nothing Then
                hadPitches = (pitchList.Count > 0)
                For i = 1 To pitchList.Count
                    Set pitch = pitchList(i)
                    pitchNumber = pitchNumber + 1
                    gamePitchCounter = gamePitchCounter + 1
                    Set beforeState = CloneState(state)
                    runsOnPlay = 0
                    If i = pitchList.Count Then
                        Set terminalBefore = CloneState(beforeState)
                        runsOnPlay = InferRunsOnPlay(beforeState, basesAfter, outsAfter)
                        SetBasesFromJson state, basesAfter
                        state("outs") = outsAfter
                        If inningHalf = "top" Then
                            state("away_score") = SafeLong(state("away_score")) + runsOnPlay
                        Else
                            state("home_score") = SafeLong(state("home_score")) + runsOnPlay
                        End If
                        state("balls") = 0
                        state("strikes") = 0
                    Else
                        ApplyNonTerminalPitch state, JsonText(pitch, "r")
                    End If
                    Set afterState = CloneState(state)
                    eventSeq = eventSeq + 1
                    events.Add MakeEventRow(gameRow, eventSeq, paId, "pitch", JsonText(pitch, "r"), _
                        PitchDescription(JsonText(pitch, "r"), JsonText(pa, "result")), pa, beforeState, afterState, runsOnPlay, paStatus)
                    pitches.Add MakePitchRow(gameRow, eventSeq, paId, pitchNumber, gamePitchCounter, pa, pitch, beforeState, afterState, runsOnPlay, (i = pitchList.Count), paStatus)
                Next i
            End If

            If terminalBefore Is Nothing Then
                Set terminalBefore = CloneState(state)
                runsOnPlay = InferRunsOnPlay(terminalBefore, basesAfter, outsAfter)
                SetBasesFromJson state, basesAfter
                state("outs") = outsAfter
                If inningHalf = "top" Then
                    state("away_score") = SafeLong(state("away_score")) + runsOnPlay
                Else
                    state("home_score") = SafeLong(state("home_score")) + runsOnPlay
                End If
                state("balls") = 0
                state("strikes") = 0
            End If
            Set afterState = CloneState(state)
            eventSeq = eventSeq + 1
            If hadPitches Then
                events.Add MakeEventRow(gameRow, eventSeq, paId, "plate_appearance_result", JsonText(pa, "type"), _
                    JsonText(pa, "result"), pa, afterState, afterState, 0, IIf(paStatus = "ok", "informational", paStatus))
            Else
                events.Add MakeEventRow(gameRow, eventSeq, paId, "plate_appearance_result", JsonText(pa, "type"), _
                    JsonText(pa, "result"), pa, terminalBefore, afterState, runsOnPlay, paStatus)
            End If
        Next pa

NextHalf:
        Set scoreAfter = JsonObject(half, "scoreAfter")
        If Not scoreAfter Is Nothing Then
            officialAway = SafeLong(scoreAfter(1), -1)
            officialHome = SafeLong(scoreAfter(2), -1)
            If SafeLong(state("away_score")) <> officialAway Or SafeLong(state("home_score")) <> officialHome Then
                Set beforeState = CloneState(state)
                scoreRuns = (officialAway - SafeLong(state("away_score"))) + (officialHome - SafeLong(state("home_score")))
                If scoreRuns < 0 Then scoreRuns = 0
                state("away_score") = officialAway
                state("home_score") = officialHome
                Set afterState = CloneState(state)
                eventSeq = eventSeq + 1
                events.Add MakeEventRow(gameRow, eventSeq, SafeText(state("current_pa_id")), "state_adjustment", _
                    "SOURCE_SCORE_SNAPSHOT", "Score synchronized to the source half-inning snapshot.", pa, _
                    beforeState, afterState, scoreRuns, "unknown")
                unknownCount = unknownCount + 1
                sourceLimited = True
            End If
        End If
    Next half
End Sub

Private Function BuildGameRow(ByVal gameData As Object, ByVal scheduleGame As Object) As Object
    Dim row As Object, away As Object, home As Object, gameId As String
    Set row = NewDictionary()
    Set away = JsonObject(gameData, "away")
    Set home = JsonObject(gameData, "home")
    gameId = JsonText(gameData, "gameId", JsonText(scheduleGame, "gameId"))
    row("season") = SafeLong(GetConfigValue("Season", 2026), 2026)
    row("game_date") = GameDateFromId(gameId)
    row("game_id") = gameId
    row("away_team") = JsonText(scheduleGame, "away", JsonText(away, "team"))
    row("home_team") = JsonText(scheduleGame, "home", JsonText(home, "team"))
    row("stadium") = JsonText(scheduleGame, "stadium", JsonText(gameData, "stadium"))
    row("game_status") = JsonText(scheduleGame, "status", JsonText(gameData, "status"))
    row("away_score") = JsonLong(scheduleGame, "aScore", JsonLong(away, "score", -1))
    row("home_score") = JsonLong(scheduleGame, "hScore", JsonLong(home, "score", -1))
    row("is_final") = IsFinalStatus(SafeText(row("game_status")))
    row("fetched_at") = IsoNow()
    row("source_url") = SafeText(GetConfigValue("BaseURL", "https://visualbaseball.com")) & "/api/game/pbp?id=" & gameId
    row("raw_cache_path") = PendingGamePath(gameId)
    row("source_hash") = "pending"
    row("validation_status") = "PENDING"
    Set BuildGameRow = row
End Function

Private Function GameDateFromId(ByVal gameId As String) As String
    If Len(gameId) >= 8 Then GameDateFromId = Left$(gameId, 4) & "-" & Mid$(gameId, 5, 2) & "-" & Mid$(gameId, 7, 2)
End Function

Private Function MakeEventRow(ByVal gameRow As Object, ByVal eventSeq As Long, ByVal paId As String, ByVal eventType As String, ByVal eventCode As String, ByVal description As String, ByVal pa As Object, ByVal beforeState As Object, ByVal afterState As Object, ByVal runsOnEvent As Long, ByVal parseStatus As String) As Object
    Dim row As Object
    Set row = NewDictionary()
    row("game_id") = gameRow("game_id")
    row("event_seq") = eventSeq
    row("inning") = beforeState("inning")
    row("inning_half") = beforeState("inning_half")
    row("pa_id") = paId
    row("event_type") = eventType
    row("event_code") = eventCode
    row("description") = description
    row("batter_id") = JsonText(pa, "batterId")
    row("batter_name") = JsonText(pa, "batter")
    row("pitcher_id") = JsonText(pa, "pitcherId")
    row("pitcher_name") = JsonText(pa, "pitcher")
    row("runner_id") = ""
    row("runner_name") = ""
    row("from_base") = ""
    row("to_base") = ""
    row("is_out") = (SafeLong(afterState("outs")) > SafeLong(beforeState("outs")))
    row("is_run") = (runsOnEvent > 0)
    row("outs_before") = beforeState("outs")
    row("outs_after") = afterState("outs")
    row("base_state_before") = BaseStateText(beforeState)
    row("base_state_after") = BaseStateText(afterState)
    row("runs_on_event") = runsOnEvent
    row("away_score_before") = beforeState("away_score")
    row("home_score_before") = beforeState("home_score")
    row("away_score_after") = afterState("away_score")
    row("home_score_after") = afterState("home_score")
    row("parse_status") = parseStatus
    Set MakeEventRow = row
End Function

Private Function MakeSubstitutionEvent(ByVal gameRow As Object, ByVal eventSeq As Long, ByVal paId As String, ByVal pa As Object, ByVal subItem As Object, ByVal state As Object) As Object
    Dim row As Object, snapshot As Object, description As String
    Set snapshot = CloneState(state)
    description = JsonText(subItem, "fromName") & " -> " & JsonText(subItem, "toName") & " (" & JsonText(subItem, "pos") & ")"
    Set row = MakeEventRow(gameRow, eventSeq, paId, "substitution", JsonText(subItem, "t"), description, pa, snapshot, snapshot, 0, "source_limited")
    row("runner_id") = JsonText(subItem, "toId")
    row("runner_name") = JsonText(subItem, "toName")
    Set MakeSubstitutionEvent = row
End Function

Private Function MakePitchRow(ByVal gameRow As Object, ByVal eventSeq As Long, ByVal paId As String, ByVal pitchNumber As Long, ByVal gamePitchNumber As Long, ByVal pa As Object, ByVal pitch As Object, ByVal beforeState As Object, ByVal afterState As Object, ByVal runsOnPitch As Long, ByVal isTerminal As Boolean, ByVal parseStatus As String) As Object
    Dim row As Object, code As String, stuff As String, kmh As Double, resultText As String
    Dim battingTeam As String, pitchingTeam As String
    Set row = NewDictionary()
    code = JsonText(pitch, "r")
    stuff = JsonText(pitch, "stuff")
    kmh = JsonDouble(pitch, "spd")
    resultText = PitchDescription(code, JsonText(pa, "result"))
    If SafeText(beforeState("inning_half")) = "top" Then
        battingTeam = gameRow("away_team"): pitchingTeam = gameRow("home_team")
    Else
        battingTeam = gameRow("home_team"): pitchingTeam = gameRow("away_team")
    End If

    row("season") = gameRow("season"): row("game_date") = gameRow("game_date"): row("game_id") = gameRow("game_id")
    row("event_seq") = eventSeq: row("pa_id") = paId
    row("pitch_id") = gameRow("game_id") & "-" & paId & "-" & Format$(pitchNumber, "00")
    row("pitch_number") = pitchNumber: row("inning") = beforeState("inning"): row("inning_half") = beforeState("inning_half")
    row("batter_id") = JsonText(pa, "batterId"): row("batter_name") = JsonText(pa, "batter")
    row("pitcher_id") = JsonText(pa, "pitcherId"): row("pitcher_name") = JsonText(pa, "pitcher")
    AddPitchState row, beforeState, afterState, runsOnPitch
    row("pitch_type") = PitchTypeEnglish(stuff): row("velocity") = kmh
    row("px") = JsonDouble(pitch, "px"): row("pz") = JsonDouble(pitch, "pz")
    row("pitch_call_code") = code: row("pitch_result") = resultText: row("pa_result") = JsonText(pa, "result")
    row("description") = resultText
    row("is_swing") = (code = "S" Or code = "F" Or code = "X")
    row("is_take") = (code = "B" Or code = "T")
    row("is_contact") = (code = "F" Or code = "X")
    row("is_in_play") = (code = "X")
    row("is_pa_terminal") = isTerminal
    row("parse_status") = parseStatus: row("fetched_at") = gameRow("fetched_at"): row("source_url") = gameRow("source_url")
    row("pitch_type_code") = PitchTypeCode(stuff): row("pitch_type_kr") = stuff
    row("velocity_kmh") = kmh: row("velocity_mph") = Round(kmh * 0.621371, 1)
    row("sz_top") = JsonDouble(pitch, "szTop"): row("sz_bottom") = JsonDouble(pitch, "szBot")
    row("release_height_cm") = JsonDouble(pitch, "relH"): row("arrival_time_s") = JsonDouble(pitch, "time")
    row("vertical_movement_cm") = JsonDouble(pitch, "vMov"): row("horizontal_movement_cm") = JsonDouble(pitch, "hMov")
    row("drop_angle") = JsonDouble(pitch, "dropAngle")
    row("x0") = JsonDouble(pitch, "x0"): row("z0") = JsonDouble(pitch, "z0")
    row("vx0") = JsonDouble(pitch, "vx0"): row("vy0") = JsonDouble(pitch, "vy0"): row("vz0") = JsonDouble(pitch, "vz0")
    row("ax") = JsonDouble(pitch, "ax"): row("ay") = JsonDouble(pitch, "ay"): row("az") = JsonDouble(pitch, "az")

    row("Rk.") = "": row("Pitcher") = row("pitcher_name"): row("Batter") = row("batter_name")
    row("Game Pitch #") = gamePitchNumber: row("Pitch") = pitchNumber: row("PA") = Replace$(paId, gameRow("game_id") & "-", "")
    row("Inn.") = row("inning"): row("Result") = resultText: row("Pitch Type") = row("pitch_type")
    row("Pitch Velo (MPH)") = row("velocity_mph"): row("IVB (in)") = Round(JsonDouble(pitch, "vMov") / 2.54, 1)
    row("Drop (in)") = Round((JsonDouble(pitch, "z0") - JsonDouble(pitch, "pz")) * 12, 1)
    row("HBreak (in)") = Round(JsonDouble(pitch, "hMov") / 2.54, 1)
    row("Date") = row("game_date"): row("Game ID") = row("game_id"): row("Stadium") = gameRow("stadium")
    row("Pitcher Team") = pitchingTeam: row("Pitcher ID") = row("pitcher_id")
    row("Batter Team") = battingTeam: row("Batter ID") = row("batter_id")
    row("Half") = IIf(row("inning_half") = "top", "Top", "Bottom")
    row("PA Result") = row("pa_result"): row("Pitch Call Code") = code: row("Pitch Code") = row("pitch_type_code")
    row("Pitch Type KR") = stuff: row("Pitch Velo (km/h)") = kmh
    row("px_cm") = Round(JsonDouble(pitch, "px") * 30.48, 2): row("pz_cm") = Round(JsonDouble(pitch, "pz") * 30.48, 2)
    row("Release Height (cm)") = row("release_height_cm"): row("Arrival Time (s)") = row("arrival_time_s")
    row("Vertical Movement (cm)") = row("vertical_movement_cm"): row("Horizontal Movement (cm)") = row("horizontal_movement_cm")
    row("Drop Angle") = row("drop_angle")
    Set MakePitchRow = row
End Function

Private Sub AddPitchState(ByVal row As Object, ByVal beforeState As Object, ByVal afterState As Object, ByVal runsOnPitch As Long)
    row("balls_before") = beforeState("balls"): row("strikes_before") = beforeState("strikes"): row("outs_before") = beforeState("outs")
    row("runner_on_1b_before") = beforeState("runner_1b_id"): row("runner_on_2b_before") = beforeState("runner_2b_id"): row("runner_on_3b_before") = beforeState("runner_3b_id")
    row("base_state_before") = BaseStateText(beforeState): row("away_score_before") = beforeState("away_score"): row("home_score_before") = beforeState("home_score")
    row("balls_after") = afterState("balls"): row("strikes_after") = afterState("strikes"): row("outs_after") = afterState("outs")
    row("runner_on_1b_after") = afterState("runner_1b_id"): row("runner_on_2b_after") = afterState("runner_2b_id"): row("runner_on_3b_after") = afterState("runner_3b_id")
    row("base_state_after") = BaseStateText(afterState): row("runs_on_pitch") = runsOnPitch
    row("away_score_after") = afterState("away_score"): row("home_score_after") = afterState("home_score")
    row("base_state_code_before") = BaseStateCode(beforeState): row("re24_state_code_before") = Re24StateCode(beforeState): row("re288_state_code_before") = Re288StateCode(beforeState)
    row("base_state_code_after") = BaseStateCode(afterState): row("re24_state_code_after") = Re24StateCode(afterState): row("re288_state_code_after") = Re288StateCode(afterState)
End Sub

Private Function PitchDescription(ByVal code As String, ByVal paResult As String) As String
    Select Case UCase$(code)
        Case "B": PitchDescription = "Ball"
        Case "F": PitchDescription = "Foul"
        Case "S": PitchDescription = "Swinging Strike"
        Case "T": PitchDescription = "Called Strike"
        Case "X": PitchDescription = paResult
        Case Else: PitchDescription = code
    End Select
End Function

Private Function PaParseStatus(ByVal paType As String) As String
    Select Case LCase$(paType)
        Case "bb", "hit", "k", "out", "hbp", "error", "fc", "sac", "hr"
            PaParseStatus = "ok"
        Case Else
            PaParseStatus = "unknown"
    End Select
End Function

Private Function PitchTypeCode(ByVal stuff As String) As String
    If MatchesUnicode(stuff, &HC9C1, &HAD6C) Or MatchesUnicode(stuff, &HD3EC, &HC2EC) Then
        PitchTypeCode = "FF"
    ElseIf MatchesUnicode(stuff, &HD22C, &HC2EC) Then
        PitchTypeCode = "FT"
    ElseIf MatchesUnicode(stuff, &HC2AC, &HB77C, &HC774, &HB354) Then
        PitchTypeCode = "SL"
    ElseIf MatchesUnicode(stuff, &HCEE4, &HD130) Then
        PitchTypeCode = "FC"
    ElseIf MatchesUnicode(stuff, &HCCB4, &HC778, &HC9C0, &HC5C5) Then
        PitchTypeCode = "CH"
    ElseIf MatchesUnicode(stuff, &HCEE4, &HBE0C) Then
        PitchTypeCode = "CU"
    ElseIf MatchesUnicode(stuff, &HC2F1, &HCEE4) Then
        PitchTypeCode = "SI"
    ElseIf MatchesUnicode(stuff, &HD3EC, &HD06C) Then
        PitchTypeCode = "FS"
    ElseIf MatchesUnicode(stuff, &HC2A4, &HC704, &HD37C) Then
        PitchTypeCode = "ST"
    Else
        PitchTypeCode = "UN"
    End If
End Function

Private Function PitchTypeEnglish(ByVal stuff As String) As String
    Select Case PitchTypeCode(stuff)
        Case "FF": PitchTypeEnglish = "4-Seam Fastball"
        Case "FT": PitchTypeEnglish = "2-Seam Fastball"
        Case "SL": PitchTypeEnglish = "Slider"
        Case "FC": PitchTypeEnglish = "Cutter"
        Case "CH": PitchTypeEnglish = "Changeup"
        Case "CU": PitchTypeEnglish = "Curveball"
        Case "SI": PitchTypeEnglish = "Sinker"
        Case "FS": PitchTypeEnglish = "Forkball"
        Case "ST": PitchTypeEnglish = "Sweeper"
        Case Else: PitchTypeEnglish = stuff
    End Select
End Function

Private Function MatchesUnicode(ByVal value As String, ParamArray codePoints() As Variant) As Boolean
    Dim i As Long, expected As String
    For i = LBound(codePoints) To UBound(codePoints)
        expected = expected & ChrW$(CLng(codePoints(i)))
    Next i
    MatchesUnicode = (value = expected)
End Function
