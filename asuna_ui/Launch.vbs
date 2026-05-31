Set WshShell = CreateObject("WScript.Shell")
' Запускаємо твій батнік, аргумент 0 означає "приховане вікно"
WshShell.Run "cmd /c ASUNA.bat", 0, False