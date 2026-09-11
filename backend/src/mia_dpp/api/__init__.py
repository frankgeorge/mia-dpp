"""Stable API module exposing the configured FastAPI application.

The module alias preserves existing ``mia_dpp.api`` imports and test
monkeypatching while route implementation lives in ``api.routes``.
"""

import sys

from mia_dpp.api import routes as _routes

sys.modules[__name__] = _routes
