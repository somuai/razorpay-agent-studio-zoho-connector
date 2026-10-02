"""Inspect local Zoho token-cache metadata without making network requests."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    """Print token-cache presence, permissions, key names and expiry only."""
    load_dotenv()
    token_path = Path(os.environ.get("ZOHO_TOKEN_FILE", ".zoho_token.json"))
    try:
        info = token_path.stat()
    except OSError:
        print("Token file: missing")
        print("Cached access token: unavailable")
        print("Access token minutes remaining: unavailable")
        return

    mode = stat.S_IMODE(info.st_mode)
    print("Token file: present")
    print(f"Permissions: {mode:04o}")
    try:
        value = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("Token file JSON: invalid or unreadable")
        print("Key names: unavailable")
        print("Cached access token: unavailable")
        print("Access token minutes remaining: unavailable")
        return

    if not isinstance(value, dict):
        print("Token file JSON: top-level value is not an object")
        print("Key names: unavailable")
        print("Cached access token: unavailable")
        print("Access token minutes remaining: unavailable")
        return

    print("Key names: " + ", ".join(sorted(str(key) for key in value)))
    token_present = isinstance(value.get("access_token"), str) and bool(value["access_token"])
    print(f"Cached access token: {'present' if token_present else 'absent'}")
    client_id = os.environ.get("ZOHO_CLIENT_ID", "")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
    if client_id and client_secret and value.get("client_credentials_fingerprint"):
        fingerprint = hashlib.sha256(f"{client_id}\0{client_secret}".encode()).hexdigest()
        matches = value["client_credentials_fingerprint"] == fingerprint
        print(
            f"Cached access token matches configured client credentials: {'yes' if matches else 'no'}"
        )
    else:
        print("Cached access token credential binding: unavailable")
    try:
        minutes_left = (float(value.get("expires_at", 0)) - time.time()) / 60.0
    except (TypeError, ValueError):
        print("Access token minutes remaining: unavailable")
    else:
        print(f"Access token minutes remaining: {max(0.0, minutes_left):.1f}")
        if token_present and minutes_left <= 0:
            print("Cached access token state: expired")


if __name__ == "__main__":
    main()
