' SARATHI Silent Background Launcher
' Runs SARATHI on Windows boot with zero console window pop-ups
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

exePath = scriptDir & "\dist\Sarathi\Sarathi.exe"
If fso.FileExists(exePath) Then
    cmd = """" & exePath & """ --background"
Else
    cmd = """" & scriptDir & "\.venv\Scripts\pythonw.exe"" """ & scriptDir & "\main.py"" --background"
End If

WshShell.Run cmd, 0, False
