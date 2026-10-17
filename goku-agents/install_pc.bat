@echo off
rem Run as Administrator on each club PC.
rem The folder with this file must also contain: pc_agent.py, lock_screen.py, agent_config.json, lock_config.json (from configs\PCxx\).
set DIR=C:\goku
if not exist %DIR% mkdir %DIR%
copy /Y "%~dp0pc_agent.py" %DIR%\ >nul
copy /Y "%~dp0lock_screen.py" %DIR%\ >nul
copy /Y "%~dp0agent_config.json" %DIR%\ >nul
copy /Y "%~dp0lock_config.json" %DIR%\ >nul
rem agent_config.json holds the PC secret: only SYSTEM and Administrators may read it
icacls "%DIR%\agent_config.json" /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F >nul
for /f "delims=" %%i in ('where pythonw') do set PYW=%%i
schtasks /Create /TN "GokuAgent" /TR "\"%PYW%\" %DIR%\pc_agent.py" /SC ONSTART /RU SYSTEM /F
schtasks /Run /TN "GokuAgent"
rem lock screen starts for every user at logon
set STARTUP=%ProgramData%\Microsoft\Windows\Start Menu\Programs\StartUp
echo @start "" "%PYW%" %DIR%\lock_screen.py> "%STARTUP%\goku_lock.bat"
echo Installed. Log off and on again (or restart) to start the lock screen.
pause
