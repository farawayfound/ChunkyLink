@echo off
REM Deploy-ToMCP.bat
REM Usage: Deploy-ToMCP.bat file1 file2 ...
REM Example: Deploy-ToMCP.bat mcp_server/tools/search_jira.py Searches/Connectors/jira_query.py
REM Omit arguments to restart the service only.

setlocal enabledelayedexpansion

set SCRIPT=%~dp0Deploy-ToMCP.ps1
set FILES=

:loop
if "%~1"=="" goto run
set FILES=!FILES!'%~1',
shift
goto loop

:run
if "!FILES!"=="" (
    powershell -ExecutionPolicy Bypass -Command "& '%SCRIPT%' -RestartService"
) else (
    set FILES=!FILES:~0,-1!
    powershell -ExecutionPolicy Bypass -Command "& '%SCRIPT%' -Files @(!FILES!) -RestartService"
)
