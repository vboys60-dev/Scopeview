@echo off
REM Windows 打包腳本（待 Win10 實機驗證）
REM 執行環境需求：Python 3.10+、Microsoft Edge WebView2 Runtime（Win10 需另裝；執行打包出的程式也需要）
REM 於專案根目錄雙擊或執行 packaging\build_win.bat
chcp 65001 >nul
cd /d "%~dp0\.." || exit /b 1
python -m venv .venv-web || exit /b 1
call .venv-web\Scripts\activate.bat || exit /b 1
python -m pip install --upgrade pip || exit /b 1
pip install -r requirements-web.txt pyinstaller || exit /b 1
pyinstaller --noconfirm --distpath dist --workpath build packaging\scope_tool_web.spec || exit /b 1
echo 完成：dist\scope_tool_web\scope_tool_web.exe
