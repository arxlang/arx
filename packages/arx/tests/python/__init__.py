"""
title: Python test package for arx.
"""

import os

# Enable before conftest/compiler imports and inherit in compiler subprocesses.
os.environ["ARX_RUNTIME_TYPECHECK"] = "1"
