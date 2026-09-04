@echo off
chcp 65001 >nul
title Push Baan Kru Aoy website
cd /d "%~dp0"

echo ==========================================================
echo    Push to GitHub  ^-^>  Vercel will deploy automatically
echo ==========================================================
echo.

git config core.pager cat >nul 2>&1
git --version >nul 2>&1
if errorlevel 1 goto NOGIT

REM ---- remove old static-site files that are no longer used ----
if exist "index.html"     del /q "index.html"
if exist "portal.html"    del /q "portal.html"
if exist "Code.gs"        del /q "Code.gs"
if exist "deploy.py"      del /q "deploy.py"
if exist "deploy.bat"     del /q "deploy.bat"
if exist "deploy-log.txt" del /q "deploy-log.txt"
if exist "bankruaoy-site" rmdir /s /q "bankruaoy-site"
if exist "img"            rmdir /s /q "img"

echo Checking changes...
git add -A
git --no-pager diff --cached --quiet
if not errorlevel 1 goto NOCHANGE

echo.
git --no-pager diff --cached --name-status
echo.

for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm\""') do set "STAMP=%%i"
git commit -m "update site %STAMP%" >nul
if errorlevel 1 goto FAILCOMMIT

echo Pushing to GitHub...
git push
if errorlevel 1 goto FAILPUSH

echo.
echo ==========================================================
echo    DONE - pushed successfully
echo ==========================================================
echo.
echo    Vercel is building now. Wait 1-2 minutes, then open
echo    https://bankruaoy.com
echo.
goto END

:NOCHANGE
echo.
echo    Nothing has changed - no push needed.
echo.
goto END

:NOGIT
echo.
echo    *** Git is not installed ***
echo    Install from https://git-scm.com/download/win
echo.
goto END

:FAILCOMMIT
echo.
echo    *** Could not commit ***
echo.
goto END

:FAILPUSH
echo.
echo    *** Push failed ***
echo    If this is the first push, a GitHub sign-in window appears.
echo    Sign in, then run push.bat again.
echo.

:END
pause
