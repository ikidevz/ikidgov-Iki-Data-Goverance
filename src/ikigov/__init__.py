"""Compatibility alias for the historical ikigov package name."""

from pathlib import Path
import sys

import ikidgov

__all__ = ["ikidgov"]

if getattr(ikidgov, "__path__", None) is not None:
    __path__ = list(ikidgov.__path__)

sys.modules.setdefault("ikigov", ikidgov)
