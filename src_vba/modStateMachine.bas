Attribute VB_Name = "modStateMachine"
Option Explicit

Public Function NewGameState() As Object
    Dim state As Object
    Set state = NewDictionary()
    state("inning") = 0
    state("inning_half") = ""
    state("balls") = 0
    state("strikes") = 0
    state("outs") = 0
    state("runner_1b_id") = ""
    state("runner_1b_name") = ""
    state("runner_2b_id") = ""
    state("runner_2b_name") = ""
    state("runner_3b_id") = ""
    state("runner_3b_name") = ""
    state("away_score") = 0
    state("home_score") = 0
    state("current_pa_id") = ""
    Set NewGameState = state
End Function

Public Sub BeginHalfInning(ByVal state As Object, ByVal inning As Long, ByVal inningHalf As String)
    state("inning") = inning
    state("inning_half") = inningHalf
    state("balls") = 0
    state("strikes") = 0
    state("outs") = 0
    ClearBases state
End Sub

Public Sub ClearBases(ByVal state As Object)
    state("runner_1b_id") = "": state("runner_1b_name") = ""
    state("runner_2b_id") = "": state("runner_2b_name") = ""
    state("runner_3b_id") = "": state("runner_3b_name") = ""
End Sub

Public Sub SetBasesFromJson(ByVal state As Object, ByVal bases As Object)
    SetOneBase state, bases, "b1", "1b"
    SetOneBase state, bases, "b2", "2b"
    SetOneBase state, bases, "b3", "3b"
End Sub

Private Sub SetOneBase(ByVal state As Object, ByVal bases As Object, ByVal jsonKey As String, ByVal stateSuffix As String)
    Dim runner As Object
    Set runner = Nothing
    On Error Resume Next
    If Not bases Is Nothing Then
        If bases.Exists(jsonKey) Then Set runner = bases(jsonKey)
    End If
    On Error GoTo 0
    If runner Is Nothing Then
        state("runner_" & stateSuffix & "_id") = ""
        state("runner_" & stateSuffix & "_name") = ""
    Else
        state("runner_" & stateSuffix & "_id") = JsonText(runner, "id")
        state("runner_" & stateSuffix & "_name") = JsonText(runner, "name")
    End If
End Sub

Public Function BaseStateText(ByVal state As Object) As String
    BaseStateText = IIf(Len(state("runner_1b_id")) > 0, "1", "-") & _
                    IIf(Len(state("runner_2b_id")) > 0, "2", "-") & _
                    IIf(Len(state("runner_3b_id")) > 0, "3", "-")
End Function

Public Function BaseStateCode(ByVal state As Object) As Long
    If Len(state("runner_1b_id")) > 0 Then BaseStateCode = BaseStateCode + 1
    If Len(state("runner_2b_id")) > 0 Then BaseStateCode = BaseStateCode + 2
    If Len(state("runner_3b_id")) > 0 Then BaseStateCode = BaseStateCode + 4
End Function

Public Function Re24StateCode(ByVal state As Object) As Long
    Re24StateCode = BaseStateCode(state) * 3 + SafeLong(state("outs"))
End Function

Public Function Re288StateCode(ByVal state As Object) As Long
    Re288StateCode = ((Re24StateCode(state) * 4 + SafeLong(state("balls"))) * 3 + SafeLong(state("strikes")))
End Function

Public Function BasesMatchJson(ByVal state As Object, ByVal bases As Object) As Boolean
    Dim probe As Object
    Set probe = NewGameState()
    SetBasesFromJson probe, bases
    BasesMatchJson = (BaseStateCode(state) = BaseStateCode(probe) And _
        state("runner_1b_id") = probe("runner_1b_id") And _
        state("runner_2b_id") = probe("runner_2b_id") And _
        state("runner_3b_id") = probe("runner_3b_id"))
End Function

Public Sub ApplyNonTerminalPitch(ByVal state As Object, ByVal pitchCode As String)
    Select Case UCase$(pitchCode)
        Case "B"
            If state("balls") < 3 Then state("balls") = state("balls") + 1
        Case "S", "T"
            If state("strikes") < 2 Then state("strikes") = state("strikes") + 1
        Case "F"
            If state("strikes") < 2 Then state("strikes") = state("strikes") + 1
    End Select
End Sub

Public Function CountOccupiedBases(ByVal state As Object) As Long
    If Len(state("runner_1b_id")) > 0 Then CountOccupiedBases = CountOccupiedBases + 1
    If Len(state("runner_2b_id")) > 0 Then CountOccupiedBases = CountOccupiedBases + 1
    If Len(state("runner_3b_id")) > 0 Then CountOccupiedBases = CountOccupiedBases + 1
End Function

Public Function InferRunsOnPlay(ByVal beforeState As Object, ByVal afterBases As Object, ByVal outsAfter As Long) As Long
    Dim afterState As Object, outsAdded As Long, candidate As Long
    Set afterState = NewGameState()
    SetBasesFromJson afterState, afterBases
    outsAdded = outsAfter - SafeLong(beforeState("outs"))
    If outsAdded < 0 Then outsAdded = 0
    candidate = CountOccupiedBases(beforeState) + 1 - CountOccupiedBases(afterState) - outsAdded
    If candidate < 0 Then candidate = 0
    InferRunsOnPlay = candidate
End Function

Public Function CloneState(ByVal source As Object) As Object
    Dim result As Object, key As Variant
    Set result = NewDictionary()
    For Each key In source.Keys
        result(key) = source(key)
    Next key
    Set CloneState = result
End Function

