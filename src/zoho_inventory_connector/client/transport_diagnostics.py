"""Safe metadata for diagnosing HTTP transport failures without exception text."""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlparse

_PROXY_ENV_NAMES = frozenset({"http_proxy", "https_proxy", "all_proxy", "no_proxy"})


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
    return {
        "exception_class": type(error).__name__,
        "cause_classes": chain[1:],
        "phase": phase,
        "host": urlparse(url).hostname or "[unknown]",
        "attempt": attempt,
        "proxy_env_names": proxies,
    }
