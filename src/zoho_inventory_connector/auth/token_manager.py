"""Thread-safe and concurrency-safe TokenManager (FR-1.3, FR-1.4, FR-1.5).

Implements single-flight proactive token refresh, zero-leak secret redaction,
and mode 0600 token persistence.
"""

import asyncio
import fcntl
import hashlib
import json
import logging
import os
import tempfile
import time
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
        self._expires_at_epoch: float = 0.0
        self._api_domain: str | None = None
        self._scope: str | None = None
        credentials = f"{client_id}\0{client_secret}".encode()
        self._credentials_fingerprint = hashlib.sha256(credentials).hexdigest()
        self._lock = asyncio.Lock()
        self.refresh_call_count: int = 0  # Telemetry for single-flight assertions

        # Load token file if provided
        if self.token_file and self.token_file.exists():
            self._load_from_file()

    def __repr__(self) -> str:
        """Never expose secrets in representations (FR-1.4, NFR-1)."""
        return f"<TokenManager dc='{self.dc}' refresh_token=[REDACTED] access_token=[REDACTED]>"

    def _load_from_file(self) -> None:
        """Load stored refresh token from secure file."""
        if not self.token_file:
            return
        try:
            content = self.token_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("Token cache must contain an object")
            credentials_match = (
                data.get("client_credentials_fingerprint") == self._credentials_fingerprint
            )
            if "refresh_token" in data and not self.refresh_token:
                self.refresh_token = data["refresh_token"]
            if credentials_match and data.get("api_domain"):
                self._api_domain = data["api_domain"]
            if (
                isinstance(data.get("access_token"), str)
                and data.get("access_token")
                and credentials_match
                and float(data.get("expires_at", 0)) > time.time() + self.refresh_buffer_seconds
            ):
                self._access_token = str(data["access_token"])
                self._expires_at_epoch = float(data["expires_at"])
                self._expires_at_mono = self.clock.monotonic() + (
                    self._expires_at_epoch - time.time()
                )
        except Exception as e:
            _logger.warning("Failed to load token file: %s", type(e).__name__)

    def save_tokens_to_file(self) -> None:
        """Atomically persist tokens while serializing writers across processes."""
        if not self.token_file or not self.refresh_token:
            return

        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.token_file.with_name(self.token_file.name + ".lock")
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        os.fchmod(lock_fd, 0o600)
        tmp_path: str | None = None
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            existing: dict[str, object] = {}
            try:
                old = json.loads(self.token_file.read_text(encoding="utf-8"))
                if isinstance(old, dict):
                    existing = old
            except (OSError, ValueError):
                # A missing or malformed cache must not block a fresh valid write.
                pass

            payload = {
                **existing,
                "refresh_token": self.refresh_token,
                "api_domain": self._api_domain,
                "access_token": self._access_token,
                "expires_at": time.time()
                + max(0.0, self._expires_at_mono - self.clock.monotonic()),
                "client_credentials_fingerprint": self._credentials_fingerprint,
            }
            payload.pop("client_id_fingerprint", None)
            file_fd, tmp_path = tempfile.mkstemp(
                prefix=f".{self.token_file.name}.",
                suffix=".tmp",
                dir=self.token_file.parent,
            )
            os.fchmod(file_fd, 0o600)
            with os.fdopen(file_fd, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_path, self.token_file)
            tmp_path = None
            directory_fd = os.open(self.token_file.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

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

            # A 401 proves the cached bearer token is unusable. Clear it before
            # refreshing so a failed refresh cannot make later calls reuse it.
            if force_refresh:
                self.invalidate_access_token(persist=True)

            # Perform single refresh call
            self.refresh_call_count += 1
            response = await refresh_access_token(
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
                accounts_base_url=self.accounts_base_url,
                client=self._http_client,
            )

            rotated_refresh_token = response.get("refresh_token")
            if isinstance(rotated_refresh_token, str) and rotated_refresh_token:
                self.refresh_token = rotated_refresh_token

            new_token = response.get("access_token")
            if not new_token:
                raise AuthError(
                    message="Zoho token refresh response did not contain an access_token.",
                    agent_guidance="Zoho returned an invalid token response; reconnect the merchant account.",
                )

            expires_in = float(response.get("expires_in", 3600))
            self._access_token = new_token
            self._expires_at_mono = self.clock.monotonic() + expires_in
            self._expires_at_epoch = time.time() + expires_in

            # Update dynamic api_domain if returned (FR-1.5)
            if "api_domain" in response:
                self._api_domain = response["api_domain"]
            if "scope" in response:
                self._scope = str(response["scope"])

            # Save refreshed metadata to disk if file configured
            if self.token_file:
                self.save_tokens_to_file()

            return self._access_token

    def invalidate_access_token(self, *, persist: bool = False) -> None:
        """Forget a rejected cached access token, preserving refresh credentials."""
        self._access_token = None
        self._expires_at_mono = 0.0
        self._expires_at_epoch = 0.0
        if persist:
            self.save_tokens_to_file()
