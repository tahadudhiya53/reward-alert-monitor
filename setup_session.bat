@echo off
setlocal
echo [1/3] Installing Python packages...
py -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo [2/3] Installing Chromium for Playwright...
py -m playwright install chromium
if errorlevel 1 goto :error
echo [3/3] Opening PlayToEarn login...
py setup_session.py
if errorlevel 1 goto :error
echo.
echo Session saved to playwright\auth.json
echo Now create the Base64 GitHub secret using:
echo.
echo powershell -NoProfile -Command "[Convert]::ToBase64String([IO.File]::ReadAllBytes('playwright\auth.json')) ^| Set-Clipboard"
echo.
pause
exit /b 0
:error
echo.
echo Something failed. Check the message above.
pause
exit /b 1
