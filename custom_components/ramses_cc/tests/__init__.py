"""Tests for RAMSES_CC integration."""

from pathlib import Path
import sys

try:
    from custom_components.ramses_cc.const import DOMAIN

except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).parent.parent.parent.parent))

    from custom_components.ramses_cc.const import DOMAIN  # noqa: F401
