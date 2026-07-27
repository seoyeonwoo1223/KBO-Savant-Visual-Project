Attribute VB_Name = "modHttp"
Option Explicit

Private mBaseUrl As String
Private mCookieHeader As String
Private mApiToken As String

Public Sub ResetHttpSession()
    mCookieHeader = ""
    mApiToken = ""
    mBaseUrl = SafeText(GetConfigValue("BaseURL", "https://visualbaseball.com"))
End Sub

Public Sub BootstrapHttpSession()
    Dim body As String, statusCode As Long, headers As String
    Dim marker As String, p As Long, q As Long
    ResetHttpSession
    body = SendGet(mBaseUrl & "/schedule", "", "", statusCode, headers)
    If statusCode <> 200 Or Len(body) = 0 Then Err.Raise vbObjectError + 2101, "BootstrapHttpSession", "Session page request failed: HTTP " & statusCode
    mCookieHeader = ExtractCookies(headers)
    marker = "<meta name=""api-token"" content="""
    p = InStr(1, body, marker, vbTextCompare)
    If p = 0 Then Err.Raise vbObjectError + 2102, "BootstrapHttpSession", "Public API token was not present in the session page."
    p = p + Len(marker)
    q = InStr(p, body, """")
    If q = 0 Then Err.Raise vbObjectError + 2103, "BootstrapHttpSession", "Public API token was malformed."
    mApiToken = Mid$(body, p, q - p)
End Sub

Public Function HttpGetJson(ByVal apiPath As String, ByVal refererPath As String) As String
    Dim attempt As Long, maxRetries As Long, statusCode As Long
    Dim headers As String, body As String, delayMs As Long, lastError As String
    maxRetries = SafeLong(GetConfigValue("MaxRetries", 3), 3)
    If maxRetries < 1 Then maxRetries = 1
    If maxRetries > 3 Then maxRetries = 3
    delayMs = SafeLong(GetConfigValue("RequestIntervalMs", 1000), 1000)
    If Len(mApiToken) = 0 Then BootstrapHttpSession

    For attempt = 1 To maxRetries
        On Error Resume Next
        body = SendGet(mBaseUrl & apiPath, mBaseUrl & refererPath, mApiToken, statusCode, headers)
        lastError = Err.Description
        Err.Clear
        On Error GoTo 0
        If statusCode = 200 And Len(Trim$(body)) > 0 Then
            If Left$(Trim$(body), 1) = "{" Or Left$(Trim$(body), 1) = "[" Then
                HttpGetJson = body
                PauseMilliseconds delayMs
                Exit Function
            End If
            lastError = "Response was not JSON."
        ElseIf statusCode = 403 Then
            BootstrapHttpSession
            lastError = "Session token was refreshed after HTTP 403."
        ElseIf Len(lastError) = 0 Then
            lastError = "HTTP " & statusCode
        End If
        PauseMilliseconds delayMs * attempt
    Next attempt
    Err.Raise vbObjectError + 2104, "HttpGetJson", "GET failed after retries: " & apiPath & " - " & lastError
End Function

Private Function SendGet(ByVal url As String, ByVal referer As String, ByVal apiToken As String, ByRef statusCode As Long, ByRef responseHeaders As String) As String
    Dim http As Object
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.setTimeouts 15000, 15000, 30000, 30000
    http.Open "GET", url, False
    http.setRequestHeader "Accept", "application/json, text/plain, */*"
    http.setRequestHeader "User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Excel-VBA"
    If Len(referer) > 0 Then http.setRequestHeader "Referer", referer
    If Len(apiToken) > 0 Then http.setRequestHeader "X-Api-Token", apiToken
    If Len(mCookieHeader) > 0 Then http.setRequestHeader "Cookie", mCookieHeader
    http.send
    statusCode = http.Status
    responseHeaders = http.getAllResponseHeaders
    If statusCode = 200 Then SendGet = BytesToUtf8(http.responseBody) Else SendGet = SafeText(http.responseText)
End Function

Private Function ExtractCookies(ByVal headers As String) As String
    Dim line As Variant, value As String, semi As Long, result As String
    For Each line In Split(Replace$(headers, vbCr, ""), vbLf)
        If LCase$(Left$(Trim$(CStr(line)), 11)) = "set-cookie:" Then
            value = Trim$(Mid$(Trim$(CStr(line)), 12))
            semi = InStr(value, ";")
            If semi > 0 Then value = Left$(value, semi - 1)
            If Len(value) > 0 Then
                If Len(result) > 0 Then result = result & "; "
                result = result & value
            End If
        End If
    Next line
    ExtractCookies = result
End Function
