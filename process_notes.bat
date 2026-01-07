@echo off
setlocal

:: Check if an argument is provided
if "%~1"=="" (
    echo Usage: %0 "path\to\input_notes_directory"
    echo Defaulting to internal input_notes folder...
    python -m src.main
) else (
    echo Processing notes from: "%~1"
    python -m src.main --input-dir "%~1"
)

endlocal
pause
