"""QR code generation for deployed passport URLs."""

from __future__ import annotations

import base64
import io

import segno


def passport_qr_png_b64(url: str) -> str:
    """Return a base64-encoded PNG of a QR code for the given URL."""
    qr = segno.make_qr(url)
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=6, border=2)
    return base64.b64encode(buf.getvalue()).decode()
