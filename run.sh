#!/bin/bash
# Run cairnsearch with proper Python path
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src:$PYTHONPATH"
python -m cairnsearch.cli.main "$@"
