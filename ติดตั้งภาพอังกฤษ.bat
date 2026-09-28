@echo off
chcp 65001 >nul
echo กำลังแตกไฟล์ภาพลงโฟลเดอร์ static\img\eng ...
powershell -NoProfile -Command "Expand-Archive -LiteralPath '%~dp0static\img\eng_images.zip' -DestinationPath '%~dp0static\img' -Force"
if errorlevel 1 goto fail
del "%~dp0static\img\eng_images.zip"
echo เสร็จแล้ว ตอนนี้กด push.bat ได้เลย
pause
del "%~f0"
exit /b
:fail
echo แตกไฟล์ไม่สำเร็จ ลองคลิกขวาที่ static\img\eng_images.zip แล้วเลือก Extract All
pause
