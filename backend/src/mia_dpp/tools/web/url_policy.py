"""Admission policy for URLs passed to the web extraction capability."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

from mia_dpp.tools.web.models import PageLoadError, ProductUrlRejectedError

AddressResolver = Callable[[str, int], Awaitable[tuple[str, ...]]]


async def resolve_addresses(host: str, port: int) -> tuple[str, ...]:
    """Resolve a hostname without blocking the API event loop."""

    def resolve() -> tuple[str, ...]:
        try:
            answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise PageLoadError(f"could not resolve product website host {host!r}") from error
        return tuple(sorted({str(answer[4][0]) for answer in answers}))

    return await asyncio.to_thread(resolve)


class ProductUrlPolicy:
    """Allow only public HTTP(S) product pages on standard ports."""

    def __init__(self, resolver: AddressResolver = resolve_addresses) -> None:
        self._resolver = resolver

    async def validate(self, url: str) -> str:
        try:
            parsed = urlsplit(url.strip())
            port = parsed.port
        except ValueError as error:
            raise ProductUrlRejectedError("product URL is invalid") from error
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            raise ProductUrlRejectedError("product URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ProductUrlRejectedError("product URL must not contain credentials")
        effective_port = port or (443 if parsed.scheme.casefold() == "https" else 80)
        if effective_port not in {80, 443}:
            raise ProductUrlRejectedError("product URL must use port 80 or 443")
        if parsed.hostname.casefold() == "localhost" or parsed.hostname.endswith(".localhost"):
            raise ProductUrlRejectedError("local and private product URLs are not allowed")

        addresses = await self._resolver(parsed.hostname, effective_port)
        if not addresses:
            raise ProductUrlRejectedError("product website host resolved to no addresses")
        for address in addresses:
            try:
                is_public = ipaddress.ip_address(address).is_global
            except ValueError as error:
                raise ProductUrlRejectedError(
                    "product website resolved to an invalid address"
                ) from error
            if not is_public:
                raise ProductUrlRejectedError("local and private product URLs are not allowed")

        return urlunsplit(
            (
                parsed.scheme.casefold(),
                parsed.netloc,
                parsed.path or "/",
                parsed.query,
                "",
            )
        )
