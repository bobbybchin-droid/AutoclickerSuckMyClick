@echo off
title AutoClicker Pro - Build EXE
echo ============================================
echo   AutoClicker Pro - Building standalone EXE
echo ============================================
echo.

pip install pyautogui keyboard pynput pyinstaller

echo.
echo Building with PyInstaller...
echo.

pyinstaller --onefile --noconsole --name "AutoClickerPro" "%~dp0auto_clicker_pro.py"

echo.
if exist "%~dp0dist\AutoClickerPro.exe" (
    echo Build successful!
    echo EXE location: %~dp0dist\AutoClickerPro.exe
) else (
    echo Build may have failed. Check output above.
)

echo.
pause
