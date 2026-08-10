@echo off
echo Installing/updating dependencies...
pip install pyinstaller reportlab >nul 2>&1

echo Building InvoicingApp.exe...
pyinstaller --clean InvoicingApp.spec

echo.
if exist "dist\InvoicingApp.exe" (
    echo Build successful: dist\InvoicingApp.exe
) else (
    echo Build FAILED. Check output above for errors.
)
pause
