"""Tiny structured-ish logger (stdlib only)."""
from __future__ import annotations

import logging
import sys

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s"))
        root = logging.getLogger("iparty")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        _configured = True
    return logging.getLogger(f"iparty.{name}")
