@echo off
title AutoClicker Pro - Launcher
echo ============================================
echo   AutoClicker Pro - Installing dependencies
echo ============================================
echo.

pip install pyautogui keyboard pynput

echo.
echo ============================================
echo   Starting AutoClicker Pro...
echo ============================================
echo.

python "%~dp0auto_clicker_pro.py"

pause
