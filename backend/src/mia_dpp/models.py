"""Backward-compatible aggregate import for MIA models.

New code should import from focused feature modules. Legacy callers can keep
their existing imports while the public contract remains stable.
"""

from mia_dpp.domain.contracts import *  # noqa: F403
