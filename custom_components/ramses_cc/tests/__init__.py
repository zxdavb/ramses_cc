"""Tests for the RAMSES II custom component."""

import os
import sys

# ModuleNotFoundError: No module named 'custom_components'
_dir = os.path.dirname(os.path.abspath(__file__))
_dir = os.path.normpath(os.path.join(_dir, "..", "..", ".."))

if _dir not in sys.path:
    sys.path.append(_dir)
