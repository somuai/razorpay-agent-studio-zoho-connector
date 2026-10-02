"""No-network diagnostics for the local token file."""

import hashlib
import json
import time

from examples.live_token_status import main


def test_token_status_prints_metadata_only(tmp_path, monkeypatch, capsys) -> None:
    token_path = tmp_path / ".secret-token.json"
    token_path.write_text(
        json.dumps(
            {
                "refresh_token": "refresh-value-must-not-print",
                "access_token": "access-value-must-not-print",
                "api_domain": "https://www.zohoapis.in",
                "expires_at": time.time() + 1800,
                "client_credentials_fingerprint": hashlib.sha256(
                    b"client-id\0client-secret"
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    token_path.chmod(0o600)
    monkeypatch.setenv("ZOHO_TOKEN_FILE", str(token_path))
    monkeypatch.setenv("ZOHO_CLIENT_ID", "client-id")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "client-secret")

    main()

    output = capsys.readouterr().out
    assert "Token file: present" in output
    assert "Permissions: 0600" in output
    assert (
        "Key names: access_token, api_domain, client_credentials_fingerprint, expires_at, refresh_token"
        in output
    )
    assert "Cached access token: present" in output
    assert "Access token minutes remaining:" in output
    assert "matches configured client credentials: yes" in output
    assert "refresh-value-must-not-print" not in output
    assert "access-value-must-not-print" not in output
    assert "fingerprint-value-must-not-print" not in output
