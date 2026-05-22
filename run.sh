#!/bin/bash
# Run cairnsearch with proper Python path.
# Use the installed console-script entry point to avoid the double-import
# RuntimeWarning that occurs with `python -m cairnsearch.cli.main`.
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src:$PYTHONPATH"
if command -v cairnsearch >/dev/null 2>&1; then
    exec cairnsearch "$@"
else
    exec python -m cairnsearch.cli "$@"
fi
