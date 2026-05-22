@echo off
REM ===========================================================================
REM  cairnsearch one-click installer (Windows)
REM
REM  Automates setup so non-developer users can get running with one command:
REM
REM      install.bat
REM
REM  It will:
REM    1. check for Python 3.11+
REM    2. install cairnsearch into a local virtual environment (.venv)
REM    3. check for Ollama and pull the default models (if Ollama is present)
REM    4. print how to start the server
REM ===========================================================================
setlocal enabledelayedexpansion

set "REPO_DIR=%~dp0"
set "VENV_DIR=%REPO_DIR%.venv"
set "DEFAULT_LLM=llama3.1:8b"
set "DEFAULT_EMBED=nomic-embed-text"

echo ==^> Checking for Python 3.11+ ...
set "PYTHON_BIN="
for %%P in (python py) do (
    if not defined PYTHON_BIN (
        %%P -c "import sys; assert sys.version_info[:2] >= (3,11)" >nul 2>&1
        if !errorlevel! == 0 set "PYTHON_BIN=%%P"
    )
)
if not defined PYTHON_BIN (
    echo [x] Python 3.11 or newer is required but was not found.
    echo [x] Install it from https://www.python.org/downloads/ and re-run.
    exit /b 1
)
echo ==^> Using Python: %PYTHON_BIN%

echo ==^> Creating virtual environment in .venv ...
%PYTHON_BIN% -m venv "%VENV_DIR%"
call "%VENV_DIR%\Scripts\activate.bat"

echo ==^> Upgrading pip ...
python -m pip install --quiet --upgrade pip

echo ==^> Installing cairnsearch (this may take a few minutes) ...
python -m pip install --quiet -e "%REPO_DIR%"

echo ==^> Checking for Ollama ...
where ollama >nul 2>&1
if %errorlevel% == 0 (
    REM Start Ollama in the background if it is not already responding.
    curl -fsS http://localhost:11434/api/tags >nul 2>&1
    if not !errorlevel! == 0 (
        echo ==^> Starting Ollama in the background ...
        start "" /b ollama serve
        REM Give it up to ~20s to come up.
        for /l %%i in (1,1,20) do (
            timeout /t 1 /nobreak >nul
            curl -fsS http://localhost:11434/api/tags >nul 2>&1
            if !errorlevel! == 0 goto ollama_up
        )
    )
    :ollama_up
    echo ==^> Pulling default models ^(skip if present^) ...
    ollama pull %DEFAULT_LLM%
    ollama pull %DEFAULT_EMBED%
) else (
    echo [!] Ollama not found. Search works without it, but RAG question-
    echo [!] answering needs a local LLM. Install Ollama from:
    echo [!]   https://ollama.com/download
    echo [!] then re-run install.bat to pull the default models.
)

echo.
echo ==^> Installation complete.
echo.
echo cairnsearch runs fully locally by default - no document content, query,
echo or embedding leaves your machine.
echo.

REM Offer to start the server now (default yes).
set "START_NOW=Y"
set /p "START_NOW=Start cairnsearch now and open the web UI? [Y/n] "
if /i "%START_NOW%"=="n" goto skip_start

echo ==^> Starting cairnsearch at http://127.0.0.1:8080 ...
start "" http://127.0.0.1:8080
cairnsearch serve
goto end

:skip_start
echo.
echo To start cairnsearch later:
echo.
echo     call "%VENV_DIR%\Scripts\activate.bat"
echo     cairnsearch serve
echo.
echo Then open http://127.0.0.1:8080 in your browser.
echo.
echo To index a folder of documents:
echo.
echo     cairnsearch reindex %%USERPROFILE%%\Documents

:end
endlocal
