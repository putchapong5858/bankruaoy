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
if exist "CNAME"          del /q "CNAME"
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
goto VERIFY

:NOCHANGE
REM ---- no new files, but there may be commits that never reached GitHub ----
git fetch origin >nul 2>&1
set "AHEAD=0"
for /f %%n in ('git rev-list --count origin/main..HEAD 2^>nul') do set "AHEAD=%%n"
if "%AHEAD%"=="0" goto UPTODATE
echo.
echo    Found %AHEAD% commit(s) not yet on GitHub - pushing now...
git push
if errorlevel 1 goto FAILPUSH
goto VERIFY

:VERIFY
REM ---- GitHub has it. Now make sure Vercel actually DEPLOYED it ----
REM      push.bat used to stop here, so a failed Vercel build went unnoticed.
echo.
echo ==========================================================
echo    Pushed to GitHub - now checking the live site
echo ==========================================================
echo.
set "SHA="
for /f %%i in ('git rev-parse --short=7 HEAD 2^>nul') do set "SHA=%%i"
if "%SHA%"=="" goto NOSHA
echo    Commit pushed : %SHA%
echo    Waiting for Vercel to finish building (up to 4 minutes)
echo    Press Ctrl+C to stop waiting - the build keeps going anyway.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s='%SHA%'; $ok=$false; for($i=1;$i -le 24;$i++){ Start-Sleep -Seconds 10; try { $r = Invoke-RestMethod -Uri 'https://bankruaoy.com/healthz' -TimeoutSec 15; if ($r.commit -eq $s) { $ok=$true; break }; if ($r.commit) { Write-Host ('   live now: ' + $r.commit + '   waiting for: ' + $s) } else { Write-Host '   live version is older than this check - waiting' } } catch { Write-Host '   site did not answer - waiting' } }; if ($ok) { exit 0 } else { exit 1 }"
if errorlevel 1 goto SLOW
echo.
echo ==========================================================
echo    DONE - the new version is LIVE on https://bankruaoy.com
echo ==========================================================
echo.
goto END

:SLOW
echo.
echo ==========================================================
echo    *** The site is STILL showing an older version ***
echo ==========================================================
echo.
echo    The build is either still running, or it FAILED.
echo    Opening the Vercel deployments page so you can see why.
echo.
echo    Look at the top row: Ready = fine, Error = click it
echo    and read the build log.
echo.
start "" "https://vercel.com/bankruaoy/bankruaoy/deployments"
goto END

:NOSHA
echo.
echo    Pushed, but could not read the commit id to verify.
echo    Opening the Vercel deployments page instead.
echo.
start "" "https://vercel.com/bankruaoy/bankruaoy/deployments"
goto END

:UPTODATE
echo.
echo    Nothing has changed - GitHub is already up to date.
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
