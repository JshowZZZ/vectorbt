@echo off
setlocal

set "PATH=C:\Program Files\Git\bin;%PATH%"
set "AGENTSMD_CMD=%APPDATA%\npm\agentsmd.cmd"

if not exist "%AGENTSMD_CMD%" (
  echo [agentsmd] CLI not found at "%AGENTSMD_CMD%".
  echo [agentsmd] Install first: npm install -g @adiasg/agentsmd
  exit /b 1
)

call "%AGENTSMD_CMD%" %*
exit /b %ERRORLEVEL%

