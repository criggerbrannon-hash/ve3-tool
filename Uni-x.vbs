' ============================================
' UNI-X VOICE TO VIDEO - SILENT LAUNCHER
' ============================================
' Double-click file này để chạy tool
' Hoàn toàn ẩn CMD window
' ============================================

Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Get script directory
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)

' Try pythonw first (completely silent)
PythonwPath = "pythonw"
ScriptPath = ScriptDir & "\ve3_pro.py"

' Run hidden (0 = hidden window)
WshShell.Run """" & PythonwPath & """ """ & ScriptPath & """", 0, False
