@echo off
REM ---------------------------------------------------------------------------
REM  A.L.E.X launcher
REM
REM    alex                     start the web interface (default)
REM    alex --text              text-only mode in this terminal
REM    alex --server --port 8080
REM    alex --test              run diagnostics
REM
REM  %~dp0 is this file's own folder, so the launcher works from any directory
REM  and keeps working if you move the project.
REM
REM  Keep this file plain ASCII: cmd.exe reads .bat in the OEM codepage, and
REM  non-ASCII characters here get mangled into bogus commands.
REM ---------------------------------------------------------------------------

setlocal
cd /d "%~dp0"

if "%~1"=="" (
    python main.py --server
) else (
    python main.py %*
)

REM Keep the window open on failure so the traceback is readable instead of
REM vanishing with the console.
if errorlevel 1 (
    echo.
    echo ALEX exited with an error ^(code %errorlevel%^).
    pause
)

endlocal
