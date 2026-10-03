"""Safe metadata for diagnosing HTTP transport failures without exception text."""

from __future__ import annotations

import asyncio
import os
import random
from collections.abc import Awaitable, Callable, Mapping
from typing import TypeVar
from urllib.parse import urlparse

import httpx

_PROXY_ENV_NAMES = frozenset({"http_proxy", "https_proxy", "all_proxy", "no_proxy"})
SANDBOX_NETWORK_GUIDANCE = (
    "Network connection failed (not a credential error). If this is running inside a "
    "sandboxed agent or CI, outbound network may be blocked; run the command from a normal terminal."
)

DEFAULT_CONNECT_ATTEMPTS = 4
T = TypeVar("T")


def zoho_connect_attempts(environ: Mapping[str, str] | None = None) -> int:
    """Return the shared bounded connect-attempt budget (not retries after a response)."""
    env = os.environ if environ is None else environ
    raw = env.get("ZOHO_CONNECT_RETRIES", str(DEFAULT_CONNECT_ATTEMPTS))
    try:
        attempts = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("ZOHO_CONNECT_RETRIES must be an integer from 1 to 10") from exc
    if not 1 <= attempts <= 10:
        raise ValueError("ZOHO_CONNECT_RETRIES must be an integer from 1 to 10")
    return attempts


async def connect_backoff(attempt: int) -> None:
    """Jittered bounded backoff between connection attempts."""
    ceiling = min(2.0, 0.25 * (2 ** (attempt - 1)))
    await asyncio.sleep(random.uniform(0.0, ceiling))


async def request_with_connect_retries(
    request: Callable[[], Awaitable[T]],
    url: str,
    *,
    attempts: int | None = None,
    before_attempt: Callable[[], Awaitable[None]] | None = None,
    on_retry: Callable[[], Awaitable[None]] | None = None,
) -> T:
    """Retry a request only when connection establishment failed.

    HTTP responses are returned immediately. On terminal transport failure, attach
    the complete attempt history to the original exception for safe diagnostics.
    """
    budget = zoho_connect_attempts() if attempts is None else attempts
    history: list[dict[str, object]] = []
    for attempt in range(1, budget + 1):
        if before_attempt is not None:
            await before_attempt()
        try:
            return await request()
        except httpx.HTTPError as exc:
            diagnostic = transport_diagnostic(exc, url, attempt=attempt)
            phase = str(diagnostic["phase"])
            history.append({"attempt": attempt, "phase": phase})
            if not is_connect_phase_failure(exc) or attempt == budget:
                diagnostic["attempt_count"] = attempt
                diagnostic["max_attempts"] = budget
                diagnostic["attempts"] = history
                exc.zoho_attempt_count = attempt  # type: ignore[attr-defined]
                exc.zoho_transport_diagnostic = diagnostic  # type: ignore[attr-defined]
                raise
            if on_retry is not None:
                await on_retry()
            await connect_backoff(attempt)
    raise AssertionError("unreachable")


def transport_diagnostic(
    error: BaseException,
    url: str,
    attempt: int,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return only exception types, failure phase, host, retry and proxy names."""
    chain: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or current.__context__

    classes = set(chain)
    if classes & {"PoolTimeout"}:
        phase = "pool timeout"
    elif classes & {"UnsupportedProtocol"}:
        phase = "unsupported protocol"
    elif classes & {"InvalidURL"}:
        phase = "invalid URL"
    elif any(name.startswith("SSL") or name in {"SSLError", "TLSVersionError"} for name in classes):
        phase = "TLS"
    elif classes & {"ConnectError", "ConnectTimeout", "ProxyError"}:
        phase = "connect"
    elif classes & {"ReadError", "ReadTimeout", "RemoteProtocolError"}:
        phase = "read"
    elif classes & {"WriteError", "WriteTimeout"}:
        phase = "write"
    elif any(name.endswith("Timeout") for name in classes):
        phase = "connect"
    else:
        phase = "connect"

    env = os.environ if environ is None else environ
    proxies = sorted(name.upper() for name in env if name.lower() in _PROXY_ENV_NAMES)
    attached = getattr(error, "zoho_transport_diagnostic", None)
    if isinstance(attached, dict):
        return attached
    return {
        "exception_class": type(error).__name__,
        "cause_classes": chain[1:],
        "phase": phase,
        "host": urlparse(url).hostname or "[unknown]",
        "attempt": attempt,
        "attempt_count": int(getattr(error, "zoho_attempt_count", attempt)),
        "attempts": [{"attempt": attempt, "phase": phase}],
        "proxy_env_names": proxies,
        "network_context_hint": SANDBOX_NETWORK_GUIDANCE,
    }


def is_connect_phase_failure(error: BaseException) -> bool:
    """Retry only failures before HTTP request processing: connect or TLS setup."""
    phase = str(transport_diagnostic(error, "https://invalid.local", attempt=1)["phase"])
    return phase in {"connect", "TLS"}


def zoho_http_timeout() -> httpx.Timeout:
    """Use short connect timeouts while allowing a separate upstream read window."""
    return httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)
