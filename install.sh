#!/usr/bin/env bash
#
# cairnsearch one-click installer (macOS / Linux)
#
# This automates the setup that the paper describes as a single pip install,
# plus the optional local-LLM dependencies, so that non-developer users
# (lawyers, clinicians, journalists) can get running with one command:
#
#   ./install.sh
#
# It will:
#   1. check for Python 3.11+
#   2. install cairnsearch (and dependencies) into a local virtual environment
#   3. check for Ollama and pull the default models (if Ollama is present)
#   4. print how to start the server
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
DEFAULT_LLM="llama3.1:8b"
DEFAULT_EMBED="nomic-embed-text"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }

# 1. Python check ------------------------------------------------------------
say "Checking for Python 3.11+ ..."
PYTHON_BIN=""
for cand in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        ver="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
        major="${ver%%.*}"; minor="${ver##*.}"
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON_BIN="$cand"; break
        fi
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    err "Python 3.11 or newer is required but was not found."
    err "Install it from https://www.python.org/downloads/ and re-run."
    exit 1
fi
say "Using $($PYTHON_BIN --version)"

# 2. Virtual environment + install ------------------------------------------
say "Creating virtual environment in .venv ..."
"$PYTHON_BIN" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

say "Upgrading pip ..."
python -m pip install --quiet --upgrade pip

say "Installing cairnsearch (this may take a few minutes) ..."
python -m pip install --quiet -e "$REPO_DIR"

# 3. Ollama (optional, for local LLM answers) -------------------------------
ollama_ready=false
if command -v ollama >/dev/null 2>&1; then
    say "Ollama detected. Ensuring it is running ..."
    if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
        say "Starting Ollama in the background ..."
        # Launch detached so the installer can continue; log to the repo dir.
        nohup ollama serve >"$REPO_DIR/.ollama-serve.log" 2>&1 &
        # Wait (up to ~20s) for the API to come up.
        for _ in $(seq 1 20); do
            sleep 1
            if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
                break
            fi
        done
    fi

    if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
        ollama_ready=true
        say "Pulling default models (skip if already present) ..."
        ollama pull "$DEFAULT_LLM"   || warn "Could not pull $DEFAULT_LLM"
        ollama pull "$DEFAULT_EMBED" || warn "Could not pull $DEFAULT_EMBED"
    else
        warn "Ollama is installed but could not be started automatically."
        warn "Start it manually with:  ollama serve"
        warn "(see $REPO_DIR/.ollama-serve.log for details)"
    fi
else
    warn "Ollama not found. cairnsearch search works without it, but RAG"
    warn "question-answering needs a local LLM. Install Ollama from:"
    warn "  https://ollama.com/download"
    warn "then re-run ./install.sh to pull the default models."
fi

# 4. Launch ------------------------------------------------------------------
say "Installation complete."
echo ""
echo "cairnsearch runs fully locally by default — no document content, query,"
echo "or embedding leaves your machine."
echo ""

# Offer to start the server now (default yes). Skip the prompt in
# non-interactive contexts (e.g. CI) and just print instructions.
START_NOW="n"
if [ -t 0 ]; then
    printf "Start cairnsearch now and open the web UI? [Y/n] "
    read -r answer
    case "$answer" in
        [Nn]*) START_NOW="n" ;;
        *)     START_NOW="y" ;;
    esac
fi

if [ "$START_NOW" = "y" ]; then
    say "Starting cairnsearch at http://127.0.0.1:8080 ..."
    # Open the browser shortly after the server starts.
    (
        sleep 3
        if command -v open >/dev/null 2>&1; then
            open "http://127.0.0.1:8080" >/dev/null 2>&1 || true       # macOS
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://127.0.0.1:8080" >/dev/null 2>&1 || true   # Linux
        else
            python -m webbrowser "http://127.0.0.1:8080" >/dev/null 2>&1 || true
        fi
    ) &
    exec cairnsearch serve
else
    cat <<EOF

To start cairnsearch later:

    source "$VENV_DIR/bin/activate"
    cairnsearch serve

Then open http://127.0.0.1:8080 in your browser.

To index a folder of documents:

    cairnsearch reindex ~/Documents
EOF
fi
