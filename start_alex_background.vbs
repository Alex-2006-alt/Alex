' Start ALEX in the background behind your screen (no console window)
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
strDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strDir

pythonw = "C:\Users\Samiran_Bera\AppData\Local\Programs\Python\Python312\pythonw.exe"
If Not objFSO.FileExists(pythonw) Then
    pythonw = "pythonw.exe"
End If

objShell.Run """" & pythonw & """ """ & strDir & "\alex_service.pyw""", 0, False
