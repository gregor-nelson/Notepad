Windows Registry Editor Version 5.00

; Add custom "Edit with Dev Notepad" to all files
[HKEY_CLASSES_ROOT\*\shell\EditWithDevNotepad]
@="Edit with Dev Notepad"
"Icon"="C:\\Users\\Dell-001\\AppData\\Local\\Programs\\Notepad\\Notepad.exe,0"

[HKEY_CLASSES_ROOT\*\shell\EditWithDevNotepad\command]
@="\"C:\\Users\\Dell-001\\AppData\\Local\\Programs\\Notepad\\Notepad.exe\" \"%1\""

; Optional: Add it specifically for directories too
[HKEY_CLASSES_ROOT\Directory\shell\OpenWithDevNotepad]
@="Open in Dev Notepad"
"Icon"="C:\\Users\\Dell-001\\AppData\\Local\\Programs\\Notepad\\Notepad.exe,0"

[HKEY_CLASSES_ROOT\Directory\shell\OpenWithDevNotepad\command]
@="\"C:\\Users\\Dell-001\\AppData\\Local\\Programs\\Notepad\\Notepad.exe\" \"%1\""
