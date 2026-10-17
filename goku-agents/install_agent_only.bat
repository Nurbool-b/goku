@echo off
rem TEST INSTALL: only the power agent (no lock screen). Run as Administrator.
rem The folder with this file must contain: pc_agent.py and agent_config.json (from configs\PCxx\).
set DIR=C:\goku
if not exist %DIR% mkdir %DIR%
copy /Y "%~dp0pc_agent.py" %DIR%\ >nul
copy /Y "%~dp0agent_config.json" %DIR%\ >nul
icacls "%DIR%\agent_config.json" /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F >nul
for /f "delims=" %%i in ('where pythonw') do set PYW=%%i
schtasks /Create /TN "GokuAgent" /TR "\"%PYW%\" %DIR%\pc_agent.py" /SC ONSTART /RU SYSTEM /F
schtasks /Run /TN "GokuAgent"
echo Agent installed and running. To remove: schtasks /Delete /TN "GokuAgent" /F
pause
