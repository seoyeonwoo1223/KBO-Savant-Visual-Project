Attribute VB_Name = "modUtils"
Option Explicit

#If VBA7 Then
Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As LongPtr)
#Else
Private Declare Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
#End If

Public Function NewDictionary() As Object
    Set NewDictionary = CreateObject("Scripting.Dictionary")
    NewDictionary.CompareMode = vbTextCompare
End Function

Public Sub PauseMilliseconds(ByVal milliseconds As Long)
    If milliseconds > 0 Then Sleep milliseconds
    DoEvents
End Sub

Public Function IsoNow() As String
    IsoNow = Format$(Now, "yyyy-mm-dd\THH:nn:ss")
End Function

Public Function SafeText(ByVal value As Variant, Optional ByVal fallback As String = "") As String
    If IsError(value) Or IsNull(value) Or IsEmpty(value) Then
        SafeText = fallback
    Else
        SafeText = CStr(value)
    End If
End Function

Public Function SafeLong(ByVal value As Variant, Optional ByVal fallback As Long = 0) As Long
    On Error GoTo Failed
    If IsNull(value) Or IsEmpty(value) Or Len(CStr(value)) = 0 Then GoTo Failed
    SafeLong = CLng(value)
    Exit Function
Failed:
    SafeLong = fallback
End Function

Public Function SafeDouble(ByVal value As Variant, Optional ByVal fallback As Double = 0#) As Double
    On Error GoTo Failed
    If IsNull(value) Or IsEmpty(value) Or Len(CStr(value)) = 0 Then GoTo Failed
    SafeDouble = CDbl(value)
    Exit Function
Failed:
    SafeDouble = fallback
End Function

Public Function JsonText(ByVal obj As Object, ByVal key As String, Optional ByVal fallback As String = "") As String
    On Error GoTo Failed
    If obj Is Nothing Then GoTo Failed
    If Not obj.Exists(key) Then GoTo Failed
    JsonText = SafeText(obj(key), fallback)
    Exit Function
Failed:
    JsonText = fallback
End Function

Public Function JsonLong(ByVal obj As Object, ByVal key As String, Optional ByVal fallback As Long = 0) As Long
    On Error GoTo Failed
    If obj Is Nothing Then GoTo Failed
    If Not obj.Exists(key) Then GoTo Failed
    JsonLong = SafeLong(obj(key), fallback)
    Exit Function
Failed:
    JsonLong = fallback
End Function

Public Function JsonDouble(ByVal obj As Object, ByVal key As String, Optional ByVal fallback As Double = 0#) As Double
    On Error GoTo Failed
    If obj Is Nothing Then GoTo Failed
    If Not obj.Exists(key) Then GoTo Failed
    JsonDouble = SafeDouble(obj(key), fallback)
    Exit Function
Failed:
    JsonDouble = fallback
End Function

Public Function JsonBoolean(ByVal obj As Object, ByVal key As String, Optional ByVal fallback As Boolean = False) As Boolean
    On Error GoTo Failed
    If obj Is Nothing Then GoTo Failed
    If Not obj.Exists(key) Then GoTo Failed
    JsonBoolean = CBool(obj(key))
    Exit Function
Failed:
    JsonBoolean = fallback
End Function

Public Function JsonObject(ByVal obj As Object, ByVal key As String) As Object
    On Error GoTo Failed
    If obj Is Nothing Then GoTo Failed
    If Not obj.Exists(key) Then GoTo Failed
    Set JsonObject = obj(key)
    Exit Function
Failed:
    Set JsonObject = Nothing
End Function

Public Function JoinPath(ByVal leftPath As String, ByVal rightPath As String) As String
    If Right$(leftPath, 1) = "\" Then
        JoinPath = leftPath & rightPath
    Else
        JoinPath = leftPath & "\" & rightPath
    End If
End Function

Public Sub EnsureFolder(ByVal folderPath As String)
    Dim fso As Object
    Dim parentPath As String
    Set fso = CreateObject("Scripting.FileSystemObject")
    If fso.FolderExists(folderPath) Then Exit Sub
    parentPath = fso.GetParentFolderName(folderPath)
    If Len(parentPath) > 0 And Not fso.FolderExists(parentPath) Then EnsureFolder parentPath
    fso.CreateFolder folderPath
End Sub

Public Sub WriteUtf8File(ByVal filePath As String, ByVal text As String)
    Dim stream As Object
    EnsureFolder CreateObject("Scripting.FileSystemObject").GetParentFolderName(filePath)
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2
    stream.Charset = "utf-8"
    stream.Open
    stream.WriteText text
    stream.Position = 0
    stream.SaveToFile filePath, 2
    stream.Close
End Sub

Public Function ReadUtf8File(ByVal filePath As String) As String
    Dim stream As Object
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2
    stream.Charset = "utf-8"
    stream.Open
    stream.LoadFromFile filePath
    ReadUtf8File = stream.ReadText
    stream.Close
End Function

Public Function BytesToUtf8(ByVal bytes As Variant) As String
    Dim stream As Object
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 1
    stream.Open
    stream.Write bytes
    stream.Position = 0
    stream.Type = 2
    stream.Charset = "utf-8"
    BytesToUtf8 = stream.ReadText
    stream.Close
End Function

Public Function ComputeFileHash(ByVal filePath As String) As String
    Dim shell As Object, proc As Object, line As Variant, output As String
    On Error GoTo Failed
    Set shell = CreateObject("WScript.Shell")
    Set proc = shell.Exec("certutil.exe -hashfile """ & filePath & """ SHA256")
    Do While proc.Status = 0
        PauseMilliseconds 25
    Loop
    output = proc.StdOut.ReadAll
    For Each line In Split(output, vbCrLf)
        line = Replace$(Trim$(line), " ", "")
        If Len(line) = 64 Then
            ComputeFileHash = LCase$(line)
            Exit Function
        End If
    Next line
Failed:
    If Len(ComputeFileHash) = 0 Then ComputeFileHash = "unavailable"
End Function

Public Function IsFinalStatus(ByVal statusText As String) As Boolean
    Dim s As String, finalStatusKorean As String
    s = LCase$(Trim$(statusText))
    finalStatusKorean = ChrW$(&HC885) & ChrW$(&HB8CC)
    IsFinalStatus = (InStr(s, finalStatusKorean) > 0 Or s = "final")
End Function

Public Function CsvContains(ByVal csvText As String, ByVal value As String) As Boolean
    Dim item As Variant
    If Len(Trim$(csvText)) = 0 Then
        CsvContains = True
        Exit Function
    End If
    For Each item In Split(csvText, ",")
        If StrComp(Trim$(CStr(item)), value, vbTextCompare) = 0 Then
            CsvContains = True
            Exit Function
        End If
    Next item
End Function
