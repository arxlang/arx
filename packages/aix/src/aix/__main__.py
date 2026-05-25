"""
title: Entrypoint module, in case you use `python -m aix`.
"""

from aix.cli import app

if __name__ == "__main__":
    app()
