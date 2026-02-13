@echo off
REM Build Hearsay with PyInstaller (onedir mode)
REM Run from the project root: build.bat

echo Building Hearsay...

pyinstaller --noconfirm --onedir --windowed ^
    --name "Hearsay" ^
    --icon "src\assets\icon.ico" ^
    --add-data "src\assets;assets" ^
    --hidden-import "faster_whisper" ^
    --hidden-import "ctranslate2" ^
    --hidden-import "pyaudiowpatch" ^
    --hidden-import "sounddevice" ^
    --hidden-import "customtkinter" ^
    --hidden-import "pystray" ^
    --collect-all "customtkinter" ^
    --collect-all "faster_whisper" ^
    --collect-all "ctranslate2" ^
    src\hearsay\__main__.py

echo.
if %ERRORLEVEL% EQU 0 (
    echo Build succeeded! Output in dist\Hearsay\
) else (
    echo Build FAILED.
)
pause
