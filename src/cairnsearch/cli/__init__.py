"""CLI module.

Note: ``app`` is intentionally NOT imported at package import time. Importing it
here would cause a RuntimeWarning when the CLI is launched via
``python -m cairnsearch.cli.main`` (the module gets imported once as a side
effect of importing the package, then again as __main__). Import lazily instead.
"""

__all__ = ["app"]


def __getattr__(name):
    # PEP 562 lazy attribute access so `from cairnsearch.cli import app` still
    # works for library users, without forcing the import at package load.
    if name == "app":
        from .main import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
