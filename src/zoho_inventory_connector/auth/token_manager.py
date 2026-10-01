"""Thread-safe and concurrency-safe TokenManager (FR-1.3, FR-1.4, FR-1.5).

Implements single-flight proactive token refresh, zero-leak secret redaction,
and mode 0600 token persistence.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import httpx

from zoho_inventory_connector.auth.oauth import (
    get_api_base_url,
    refresh_access_token,
)
from zoho_inventory_connector.client.errors import AuthError
from zoho_inventory_connector.ratelimit.clock import Clock, SystemClock

_logger = logging.getLogger("zoho_connector.auth")

DEFAULT_REFRESH_BUFFER_SECONDS = 300.0  # Refresh 5 minutes before expiry


class TokenManager:
    """Manages Zoho OAuth token lifecycle with single-flight concurrency lock."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str | None = None,
        token_file: Path | str | None = None,
        dc: str = "in",
        accounts_base_url: str | None = None,
        clock: Clock | None = None,
        refresh_buffer_seconds: float = DEFAULT_REFRESH_BUFFER_SECONDS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_file = Path(token_file) if token_file else None
        self.dc = dc
        self.accounts_base_url = accounts_base_url
        self.clock: Clock = clock or SystemClock()
        self.refresh_buffer_seconds = refresh_buffer_seconds
        self._http_client = http_client

        self._access_token: str | None = None
        self._expires_at_mono: float = 0.0
        self._api_domain: str | None = None
        self._lock = asyncio.Lock()
        self.refresh_call_count: int = 0  # Telemetry for single-flight assertions

        # Load token file if provided
        if self.token_file and self.token_file.exists():
            self._load_from_file()

    def __repr__(self) -> str:
        """Never expose secrets in representations (FR-1.4, NFR-1)."""
        ref_masked = f"{self.refresh_token[:4]}...[REDACTED]" if self.refresh_token else "None"
        acc_masked = f"{self._access_token[:4]}...[REDACTED]" if self._access_token else "None"
        return f"<TokenManager dc='{self.dc}' refresh_token={ref_masked} access_token={acc_masked}>"

    def _load_from_file(self) -> None:
        """Load stored refresh token from secure file."""
        if not self.token_file:
            return
        try:
            content = self.token_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if "refresh_token" in data and not self.refresh_token:
                self.refresh_token = data["refresh_token"]
            if "api_domain" in data:
                self._api_domain = data["api_domain"]
        except Exception as e:
            _logger.warning("Failed to load token file: %s", type(e).__name__)

    def save_tokens_to_file(self) -> None:
        """Persist refresh token to file with 0600 permissions (FR-1.4)."""
        if not self.token_file or not self.refresh_token:
            return

        payload = {
            "refresh_token": self.refresh_token,
            "api_domain": self._api_domain,
        }
        json_data = json.dumps(payload, indent=2)

        # Atomic write with 0600 mode
        tmp_file = self.token_file.with_suffix(".tmp")
        # Ensure parent directory exists
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

        # Create file with 0600 permissions
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(str(tmp_file), flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json_data)
            os.replace(str(tmp_file), str(self.token_file))
        except Exception:
            if tmp_file.exists():
                tmp_file.unlink()
            raise

    def is_token_valid(self) -> bool:
        """Return True if current cached access token is valid and outside buffer window."""
        if not self._access_token:
            return False
        remaining = self._expires_at_mono - self.clock.monotonic()
        return remaining > self.refresh_buffer_seconds

    def get_api_base_url(self) -> str:
        """Get API base URL routed dynamically via api_domain (FR-1.5)."""
        return get_api_base_url(dc=self.dc, api_domain=self._api_domain)

    async def get_access_token(self, force_refresh: bool = False) -> str:
        """Get valid access token with single-flight concurrency lock (FR-1.3).

        If 50 concurrent requests arrive when token is expired, exactly ONE
        underlying refresh call is executed; all 49 other requests wait and
        receive the freshly minted token.
        """
        if not force_refresh and self.is_token_valid() and self._access_token:
            return self._access_token

        async with self._lock:
            # Double-checked locking pattern inside lock
            if not force_refresh and self.is_token_valid() and self._access_token:
                return self._access_token

            if not self.refresh_token:
                raise AuthError(
                    message="No refresh token configured. Run OAuth authorization or provide ZOHO_REFRESH_TOKEN.",
                    agent_guidance="Authentication failed because no refresh token is present; re-authenticate the merchant.",
                )

            # Perform single refresh call
            self.refresh_call_count += 1
            response = await refresh_access_token(
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
                accounts_base_url=self.accounts_base_url,
                client=self._http_client,
            )

            new_token = response.get("access_token")
            if not new_token:
                raise AuthError(
                    message="Zoho token refresh response did not contain an access_token.",
                    agent_guidance="Zoho returned an invalid token response; reconnect the merchant account.",
                )

            expires_in = float(response.get("expires_in", 3600))
            self._access_token = new_token
            self._expires_at_mono = self.clock.monotonic() + expires_in

            # Update dynamic api_domain if returned (FR-1.5)
            if "api_domain" in response:
                self._api_domain = response["api_domain"]

            # Save refreshed metadata to disk if file configured
            if self.token_file:
                self.save_tokens_to_file()

            return self._access_token
