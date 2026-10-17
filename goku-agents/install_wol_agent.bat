@echo off
rem Run as Administrator on the always-on device. Folder must contain wol_agent.py and wol_config.json.
set DIR=C:\goku
if not exist %DIR% mkdir %DIR%
copy /Y "%~dp0wol_agent.py" %DIR%\ >nul
copy /Y "%~dp0wol_config.json" %DIR%\ >nul
for /f "delims=" %%i in ('where pythonw') do set PYW=%%i
schtasks /Create /TN "GokuWol" /TR "\"%PYW%\" %DIR%\wol_agent.py" /SC ONSTART /RU SYSTEM /F
schtasks /Run /TN "GokuWol"
echo Done.
pause
