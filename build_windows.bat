@echo off
REM Build script for D-PPG Manager on Windows
REM Prerequisites: Python 3.10+, pip install pyinstaller numpy scipy matplotlib reportlab sqlalchemy pillow
REM Run from the project root directory

echo Installing dependencies...
pip install pyinstaller numpy scipy matplotlib reportlab sqlalchemy pillow

echo Building DPPG Manager...
pyinstaller dppg_manager.spec --clean --noconfirm

echo.
echo Done! The executable is in: dist\DPPG Manager\DPPG Manager.exe
echo To create an installer, use NSIS or Inno Setup with the dist\DPPG Manager folder.
pause
