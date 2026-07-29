Attribute VB_Name = "modCache"
Option Explicit

Public Function RawSeasonFolder() As String
    RawSeasonFolder = JoinPath(JoinPath(CacheFolderPath(), "raw"), CStr(SafeLong(GetConfigValue("Season", 2026), 2026)))
    EnsureFolder RawSeasonFolder
End Function

Public Function RawGamePath(ByVal gameId As String) As String
    RawGamePath = JoinPath(RawSeasonFolder(), gameId & ".json")
End Function

Public Function PendingGamePath(ByVal gameId As String) As String
    PendingGamePath = JoinPath(RawSeasonFolder(), gameId & ".pending.json")
End Function

Public Function LockFilePath() As String
    LockFilePath = JoinPath(CacheFolderPath(), "update.lock")
End Function

Public Sub AcquireUpdateLock()
    Dim fso As Object, lockPath As String, file As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    EnsureFolder CacheFolderPath()
    lockPath = LockFilePath()
    If fso.FileExists(lockPath) Then
        If DateDiff("h", fso.GetFile(lockPath).DateLastModified, Now) < 6 Then
            Err.Raise vbObjectError + 2201, "AcquireUpdateLock", "Another update appears to be active: " & lockPath
        End If
        fso.DeleteFile lockPath, True
    End If
    Set file = fso.CreateTextFile(lockPath, True, True)
    file.WriteLine IsoNow()
    file.WriteLine ThisWorkbook.FullName
    file.Close
End Sub

Public Sub ReleaseUpdateLock()
    Dim fso As Object, lockPath As String
    On Error Resume Next
    Set fso = CreateObject("Scripting.FileSystemObject")
    lockPath = LockFilePath()
    If fso.FileExists(lockPath) Then fso.DeleteFile lockPath, True
    On Error GoTo 0
End Sub

Public Sub SavePendingRaw(ByVal gameId As String, ByVal jsonText As String)
    WriteUtf8File PendingGamePath(gameId), jsonText
End Sub

Public Sub PromotePendingRaw(ByVal gameId As String)
    Dim fso As Object, pendingPath As String, finalPath As String
    Set fso = CreateObject("Scripting.FileSystemObject")
    pendingPath = PendingGamePath(gameId)
    finalPath = RawGamePath(gameId)
    If fso.FileExists(finalPath) Then fso.DeleteFile finalPath, True
    If fso.FileExists(pendingPath) Then fso.MoveFile pendingPath, finalPath
End Sub

Public Function RawGameExists(ByVal gameId As String) As Boolean
    RawGameExists = CreateObject("Scripting.FileSystemObject").FileExists(RawGamePath(gameId))
End Function

