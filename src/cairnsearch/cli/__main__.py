"""Entry point for `python -m cairnsearch.cli`.

Using this module (rather than `python -m cairnsearch.cli.main`) avoids the
double-import RuntimeWarning, because `main` is only imported here, not as the
module being executed.
"""
from .main import app

if __name__ == "__main__":
    app()
