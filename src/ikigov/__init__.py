"""Deprecated compatibility alias for the historical ikigov package name."""

import warnings

import ikidgov

__all__ = ["ikidgov"]

warnings.warn(
    "The 'ikigov' package name is deprecated; import 'ikidgov' instead.",
    DeprecationWarning,
    stacklevel=2,
)

if getattr(ikidgov, "__path__", None) is not None:
    __path__ = list(ikidgov.__path__)
