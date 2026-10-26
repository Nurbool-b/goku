@echo off
rem QAZGAME: run as Administrator from the extracted agents folder (the "configs" folder must be next to this file).
rem Asks for the PC number and installs the agent (+ optional lock screen) with the right keys.
set /p N=PC number: 
set N=0%N%
set N=%N:~-2%
set SRC=%~dp0configs\PC%N%
if not exist "%SRC%\agent_config.json" (
  echo Config for PC%N% not found in %~dp0configs
  pause
  exit /b 1
)
set /p LOCK=Install lock screen too? (y/n): 
set DIR=C:\qazgame
if not exist %DIR% mkdir %DIR%
copy /Y "%~dp0pc_agent.py" %DIR%\ >nul
copy /Y "%SRC%\agent_config.json" %DIR%\ >nul
icacls "%DIR%\agent_config.json" /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F >nul
for /f "delims=" %%i in ('where pythonw') do set PYW=%%i
schtasks /Create /TN "QazGameAgent" /TR "\"%PYW%\" %DIR%\pc_agent.py" /SC ONSTART /RU SYSTEM /F
schtasks /Run /TN "QazGameAgent"
if /i not "%LOCK%"=="y" goto done
copy /Y "%~dp0lock_screen.py" %DIR%\ >nul
copy /Y "%SRC%\lock_config.json" %DIR%\ >nul
echo @start "" "%PYW%" %DIR%\lock_screen.py> "%ProgramData%\Microsoft\Windows\Start Menu\Programs\StartUp\qazgame_lock.bat"
:done
echo.
echo Installed PC%N%. Restart the PC to finish.
pause
