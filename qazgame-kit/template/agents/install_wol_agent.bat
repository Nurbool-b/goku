@echo off
rem QAZGAME: run as Administrator on the always-on device (operator PC). Folder must contain wol_agent.py and wol_config.json.
set DIR=C:\qazgame
if not exist %DIR% mkdir %DIR%
copy /Y "%~dp0wol_agent.py" %DIR%\ >nul
copy /Y "%~dp0wol_config.json" %DIR%\ >nul
for /f "delims=" %%i in ('where pythonw') do set PYW=%%i
schtasks /Create /TN "QazGameWol" /TR "\"%PYW%\" %DIR%\wol_agent.py" /SC ONSTART /RU SYSTEM /F
schtasks /Run /TN "QazGameWol"
echo Done.
pause
