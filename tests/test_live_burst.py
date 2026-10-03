"""Offline orchestration tests for the terminal live-burst helper."""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "live_burst.sh"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "MOCK_PORT": str(_free_port()),
            "NET_WATCH_LIMIT_SECONDS": "3",
            "LIVE_BURST_OUTPUT_ROOT": str(tmp_path / ".live_out"),
            "PYTHON": str(ROOT / ".venv" / "bin" / "python"),
            "UVICORN": str(ROOT / ".venv" / "bin" / "uvicorn"),
        }
    )
    env.update(extra)
    return env


def test_net_watch_mock_uses_only_local_unauthenticated_hosts(tmp_path: Path) -> None:
    completed = subprocess.run(
        ["bash", str(SCRIPT), "net-watch", "--mock"],
        cwd=ROOT,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "accounts=answered-http-404" in completed.stdout
    assert "api=answered-http-401" in completed.stdout
    assert "https://accounts.zoho.in" not in completed.stdout
    assert "SAFE TO SCREENSHOT" not in completed.stdout


def test_live_burst_mock_completes_all_four_read_only_stages(tmp_path: Path) -> None:
    completed = subprocess.run(
        ["bash", str(SCRIPT), "live-burst", "--mock"],
        cwd=ROOT,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    for step in (
        "env-validation",
        "net-watch",
        "live-token-status",
        "live-preflight",
        "live-smoke",
        "live-probe",
        "live-assert",
    ):
        assert step in output
    assert "SAFE TO SCREENSHOT" in output
    assert "zoho_access_mock_token_12345" not in output
    assert "org_kaveri_blr_001" not in output
    assert "MOCK" not in (ROOT / "docs" / "LIVE_FINDINGS.md").read_text(encoding="utf-8")
    assert list((tmp_path / ".live_out").glob("*/mock-live-findings.md"))


def test_live_burst_stops_after_first_failure_and_masks_secret_output(tmp_path: Path) -> None:
    make_stub = tmp_path / "make-stub"
    calls_file = tmp_path / "make-calls.txt"
    make_stub.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$1\" >> '{calls_file}'\n"
        'case "$1" in\n'
        "  live-token-status) printf '%s\\n' 'Token file: present' 'Permissions: 0600' 'Cached access token: present' 'Cached access token matches configured client credentials: yes' 'Access token minutes remaining: 60.0'; exit 0 ;;\n"
        "  live-preflight) echo 'PASS mock preflight'; exit 0 ;;\n"
        "  live-smoke) echo 'access_token=do-not-show-this-secret'; exit 7 ;;\n"
        "  *) echo 'SHOULD_NOT_RUN'; exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    make_stub.chmod(0o755)
    completed = subprocess.run(
        ["bash", str(SCRIPT), "live-burst", "--mock"],
        cwd=ROOT,
        env=_env(tmp_path, MAKE_BIN=str(make_stub)),
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 7
    assert "do-not-show-this-secret" not in output
    assert "STOP: live-smoke failed" in output
    assert "NOT SAFE TO SCREENSHOT" in output
    calls = calls_file.read_text(encoding="utf-8").splitlines()
    assert calls == ["live-token-status", "live-preflight", "live-smoke"]
    assert "live-probe" not in calls
    assert "live-assert" not in calls
