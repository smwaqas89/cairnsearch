# cairnsearch - Windows Installation Guide

## Prerequisites

### 1. Install Python 3.11+

Download from: https://www.python.org/downloads/windows/

**Important**: During installation, check "Add Python to PATH"

Verify:
```cmd
python --version
```

### 2. Install Ollama for Windows

Download from: https://ollama.com/download/windows

After installation, open PowerShell and run:
```powershell
# Start Ollama (runs in background)
ollama serve

# In a new terminal, pull required models
ollama pull nomic-embed-text
ollama pull llama3.1:8b
```

### 3. Install Tesseract OCR (Optional - for scanned PDFs)

Download from: https://github.com/UB-Mannheim/tesseract/wiki

Add to PATH: `C:\Program Files\Tesseract-OCR`

## Installation

### Option A: Using PowerShell

```powershell
# Create project directory
cd ~\Desktop
mkdir local-doc-search
cd local-doc-search

# Extract the zip file (download first)
Expand-Archive -Path ~\Downloads\cairnsearch-with-rag.zip -DestinationPath . -Force
Move-Item .\local-doc-search\* . -Force
Remove-Item .\local-doc-search

# Create virtual environment
python -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -e .
```

### Option B: Using Command Prompt (cmd)

```cmd
cd %USERPROFILE%\Desktop
mkdir local-doc-search
cd local-doc-search

:: Extract zip file manually or use:
tar -xf %USERPROFILE%\Downloads\cairnsearch-with-rag.zip

:: Create virtual environment
python -m venv .venv

:: Activate
.venv\Scripts\activate.bat

:: Install dependencies
pip install -e .
```

## Running

### Start the Server

```powershell
# Make sure Ollama is running first
# In a separate terminal: ollama serve

# Activate venv
.\.venv\Scripts\Activate.ps1

# Set PYTHONPATH and run
$env:PYTHONPATH = ".\src"
python -m cairnsearch.cli.main serve
```

Or create `run.bat`:
```batch
@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
set PYTHONPATH=%cd%\src
python -m cairnsearch.cli.main serve %*
```

Then run:
```cmd
run.bat serve
```

### Access the UI

Open browser: http://localhost:8080

## Windows-Specific Notes

### File Paths

Windows uses backslashes (`\`) but the app handles both. When adding folders in the UI, paths like:
- `C:\Users\YourName\Documents`
- `D:\Work\Files`

Will work correctly.

### Data Location

Windows data is stored in:
```
%LOCALAPPDATA%\cairnsearch\cairnsearch.db
%LOCALAPPDATA%\cairnsearch\vectors\vectors.db
```

Or if using the default Unix-style path:
```
%USERPROFILE%\.local\share\cairnsearch\
```

### Configuration

Create config at:
```
%USERPROFILE%\.config\cairnsearch\config.toml
```

Or:
```
%APPDATA%\cairnsearch\config.toml
```

Example config:
```toml
[general]
data_dir = "~/.local/share/cairnsearch"

[rag]
enabled = true
embedding_provider = "ollama"
ollama_base_url = "http://localhost:11434"
ollama_model = "llama3.1:8b"
```

### Common Windows Issues

#### PowerShell Execution Policy

If you get "cannot be loaded because running scripts is disabled":
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Port Already in Use

```powershell
# Find process using port 8080
netstat -ano | findstr :8080

# Kill process (replace PID)
taskkill /PID <PID> /F
```

#### Ollama Not Found

Make sure Ollama is in PATH. Default location:
```
C:\Users\<YourName>\AppData\Local\Programs\Ollama
```

Add to PATH in System Environment Variables.

#### Long Path Support

If you get path errors, enable long paths in Windows:
```powershell
# Run as Administrator
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

#### Tesseract Not Found

Add Tesseract to PATH:
```powershell
$env:PATH += ";C:\Program Files\Tesseract-OCR"
```

Or set permanently in System Environment Variables.

## Running as a Service (Optional)

### Using NSSM (Non-Sucking Service Manager)

1. Download NSSM: https://nssm.cc/download

2. Install as service:
```cmd
nssm install cairnsearch
```

3. Configure:
   - Path: `C:\Users\YourName\Desktop\local-doc-search\.venv\Scripts\python.exe`
   - Startup directory: `C:\Users\YourName\Desktop\local-doc-search`
   - Arguments: `-m cairnsearch.cli.main serve`
   - Environment: `PYTHONPATH=.\src`

4. Start service:
```cmd
nssm start cairnsearch
```

### Using Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: "When the computer starts"
4. Action: Start a program
   - Program: `C:\Users\YourName\Desktop\local-doc-search\run.bat`
   - Arguments: `serve`
   - Start in: `C:\Users\YourName\Desktop\local-doc-search`

## WSL Alternative

If you prefer Linux environment, use WSL2:

```bash
# Install WSL2
wsl --install

# In WSL terminal
sudo apt update
sudo apt install python3.11 python3.11-venv tesseract-ocr

# Follow Linux installation instructions
```

## Quick Start Summary

```powershell
# 1. Start Ollama (separate terminal)
ollama serve

# 2. Pull models (first time only)
ollama pull nomic-embed-text
ollama pull llama3.1:8b

# 3. Start cairnsearch
cd ~\Desktop\local-doc-search
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = ".\src"
python -m cairnsearch.cli.main serve

# 4. Open browser
start http://localhost:8080
```

## Troubleshooting

See `TROUBLESHOOTING.md` for common issues and database queries.

For Windows-specific issues:
1. Check Windows Event Viewer for errors
2. Run PowerShell/CMD as Administrator if permission issues
3. Temporarily disable antivirus if installation fails
4. Use `python -v` for verbose Python output
