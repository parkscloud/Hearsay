@echo off
REM Build Hearsay with PyInstaller (onedir mode)
REM Run from the project root: build.bat
REM The bundle is defined by Hearsay.spec -- edit that file to change
REM bundled data, hidden imports, the icon, etc.

echo Building Hearsay...

pyinstaller --noconfirm Hearsay.spec

echo.
if %ERRORLEVEL% EQU 0 (
    echo Build succeeded! Output in dist\Hearsay\
) else (
    echo Build FAILED.
)
