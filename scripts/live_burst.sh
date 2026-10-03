#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON:-.venv/bin/python}"
MAKE_BIN="${MAKE_BIN:-make}"
CURL_BIN="${CURL_BIN:-curl}"
UVICORN_BIN="${UVICORN:-.venv/bin/uvicorn}"
MOCK_PORT="${MOCK_PORT:-18765}"
MOCK_MODE=0
MOCK_PID=""
OUT_DIR=""

usage() {
  echo "Usage: scripts/live_burst.sh {net-watch|live-burst} [--mock]"
}

cleanup() {
  if [[ -n "$MOCK_PID" ]]; then
    kill "$MOCK_PID" >/dev/null 2>&1 || true
    wait "$MOCK_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if [[ $# -lt 1 ]]; then usage; exit 2; fi
ACTION="$1"
shift
for arg in "$@"; do
  if [[ "$arg" == "--mock" ]]; then MOCK_MODE=1; else usage; exit 2; fi
done
if [[ "$ACTION" != "net-watch" && "$ACTION" != "live-burst" ]]; then usage; exit 2; fi

if [[ "$MOCK_MODE" == "1" ]]; then
  export ZOHO_LIVE_MOCK=1
  export ZOHO_CLIENT_ID="mock-client-id"
  export ZOHO_CLIENT_SECRET="mock-client-secret"
  export ZOHO_ORG_ID="org_kaveri_blr_001"
  export ZOHO_DC="in"
  export ZOHO_ACCOUNTS_BASE_URL="http://127.0.0.1:${MOCK_PORT}"
  if [[ "$ACTION" == "live-burst" ]]; then
    base_out="${LIVE_BURST_OUTPUT_ROOT:-.live_out}"
    run_id="$(date -u '+%Y%m%dT%H%M%SZ')"
    OUT_DIR="$base_out/$run_id"
    mkdir -p "$OUT_DIR"
    export ZOHO_TOKEN_FILE="$OUT_DIR/mock-private-token.json"
    export ZOHO_LIVE_FINDINGS_PATH="$OUT_DIR/mock-live-findings.md"
    export ZOHO_LIVE_EXPECTED_PATH="$OUT_DIR/mock-live-expected.json"
    printf '{"items":[{"sku":"KHG-SILK-019","expect":{"status":"out_of_stock"}}],"orders":[{"reference_number":"order_RzpKav1001","expect":{"found":true}}]}\n' > "$ZOHO_LIVE_EXPECTED_PATH"
  fi
fi

start_mock_server() {
  export ZOHO_MOCK_API_DOMAIN="http://127.0.0.1:${MOCK_PORT}"
  PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" "$UVICORN_BIN" mock_zoho.app:app \
    --host 127.0.0.1 --port "$MOCK_PORT" --log-level warning \
    >"${OUT_DIR:-/tmp}/live-burst-mock-server.log" 2>&1 &
  MOCK_PID=$!
  for _try in {1..50}; do
    if "$CURL_BIN" -sS -o /dev/null -m 1 "http://127.0.0.1:${MOCK_PORT}/" 2>/dev/null; then
      return 0
    fi
    sleep 0.1
  done
  echo "FAIL: local mock server did not become ready."
  return 1
}

seed_mock_token() {
  "$PYTHON_BIN" - "$ZOHO_TOKEN_FILE" "$ZOHO_CLIENT_ID" "$ZOHO_CLIENT_SECRET" "$ZOHO_MOCK_API_DOMAIN" <<'PY'
import hashlib
import json
import os
import sys
import time
from pathlib import Path

path, client_id, client_secret, api_domain = sys.argv[1:]
output = Path(path)
output.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "refresh_token": "zoho_refresh_mock_token_67890",
    "access_token": "zoho_access_mock_token_12345",
    "api_domain": api_domain,
    "expires_at": time.time() + 3600,
    "client_credentials_fingerprint": hashlib.sha256(
        f"{client_id}\0{client_secret}".encode()
    ).hexdigest(),
}
fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as stream:
    json.dump(payload, stream)
    stream.write("\n")
os.chmod(output, 0o600)
PY
}

net_watch_loop() {
  local limit elapsed started accounts_url api_url accounts_code api_code accounts_ok api_ok
  limit="${NET_WATCH_LIMIT_SECONDS:-600}"
  if ! [[ "$limit" =~ ^[0-9]+$ ]] || (( limit < 1 )); then
    echo "FAIL: NET_WATCH_LIMIT_SECONDS must be a positive integer."
    return 2
  fi
  if [[ "$MOCK_MODE" == "1" ]]; then
    accounts_url="http://127.0.0.1:${MOCK_PORT}/"
    api_url="http://127.0.0.1:${MOCK_PORT}/inventory/v1/organizations"
  else
    accounts_url="https://accounts.zoho.in/"
    api_url="https://www.zohoapis.in/"
  fi
  started="$(date +%s)"
  while true; do
    accounts_ok=0
    api_ok=0
    accounts_code="000"
    api_code="000"
    if accounts_code="$("$CURL_BIN" -sS -o /dev/null -m 5 -w '%{http_code}' "$accounts_url" 2>/dev/null)" \
      && [[ "$accounts_code" != "000" ]]; then accounts_ok=1; fi
    if api_code="$("$CURL_BIN" -sS -o /dev/null -m 5 -w '%{http_code}' "$api_url" 2>/dev/null)" \
      && [[ "$api_code" != "000" ]]; then api_ok=1; fi
    printf '%s accounts=%s api=%s\n' \
      "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
      "$([[ $accounts_ok == 1 ]] && echo "answered-http-${accounts_code}" || echo timeout)" \
      "$([[ $api_ok == 1 ]] && echo "answered-http-${api_code}" || echo timeout)"
    if (( accounts_ok == 1 && api_ok == 1 )); then
      echo "PASS: Zoho Accounts and Inventory hosts answered unauthenticated requests."
      return 0
    fi
    elapsed=$(( $(date +%s) - started ))
    if (( elapsed >= limit )); then
      echo "FAIL: Zoho hosts did not both answer within ${limit}s; no authenticated calls were made."
      return 1
    fi
    sleep 3
  done
}

if [[ "$ACTION" == "net-watch" ]]; then
  if [[ "$MOCK_MODE" == "1" ]]; then start_mock_server || exit 1; fi
  net_watch_loop
  exit $?
fi

# From here, live-burst runs each step into an ignored output directory.
if [[ "$MOCK_MODE" != "1" ]]; then
  run_id="$(date -u '+%Y%m%dT%H%M%SZ')"
  OUT_DIR="${LIVE_BURST_OUTPUT_ROOT:-.live_out}/$run_id"
  mkdir -p "$OUT_DIR"
fi

step_names=()
step_codes=()
step_calls=()
step_scans=()
step_files=()

count_calls() {
  local file="$1" api_sum preflight_calls
  api_sum="$(grep -Eo '"upstream_calls"[[:space:]]*:[[:space:]]*[0-9]+' "$file" 2>/dev/null | awk -F: '{sum += $2} END {print sum+0}')"
  preflight_calls="$(grep -Eo 'API calls used: [0-9]+' "$file" 2>/dev/null | awk '{value=$4} END {if (value == "") print ""; else print value}')"
  if [[ -n "$preflight_calls" ]]; then echo "$preflight_calls"; else echo "$api_sum"; fi
}

scan_file() {
  local file="$1" scan_log="$2"
  if "$PYTHON_BIN" scripts/scan_live_outputs.py "$file" >"$scan_log"; then
    echo SAFE
  else
    cat "$scan_log"
    echo UNSAFE
  fi
}

print_summary() {
  local index all_safe=1 scanfile
  echo
  echo "Live burst summary"
  printf '%-20s | %-4s | %-14s | %-8s | %s\n' "step" "exit" "upstream calls" "scan" "output"
  printf '%s\n' "---------------------+------+----------------+----------+------------------------------"
  for index in "${!step_names[@]}"; do
    printf '%-20s | %-4s | %-14s | %-8s | %s\n' \
      "${step_names[$index]}" "${step_codes[$index]}" "${step_calls[$index]}" \
      "${step_scans[$index]}" "${step_files[$index]}"
    [[ "${step_scans[$index]}" == "SAFE" ]] || all_safe=0
  done
  if (( all_safe == 1 )); then echo "SAFE TO SCREENSHOT"; else echo "NOT SAFE TO SCREENSHOT"; fi
}

run_step() {
  local name="$1"; shift
  local output_file scan_file_path rc scan_result
  output_file="$OUT_DIR/${name}.txt"
  scan_file_path="$OUT_DIR/${name}.scan.txt"
  echo "RUN: $name (output saved to $output_file)"
  if [[ "$name" == "net-watch" ]]; then
    if net_watch_loop > >(tee "$output_file") 2>&1; then rc=0; else rc=$?; fi
  elif [[ "$name" == "zoho-token" ]]; then
    # getpass reads from the controlling terminal; input is hidden and is never piped through this script.
    if "$MAKE_BIN" zoho-token >"$output_file" 2> >(tee -a "$output_file" >&2); then rc=0; else rc=$?; fi
  else
    if "$@" >"$output_file" 2>&1; then rc=0; else rc=$?; fi
  fi
  scan_result="$(scan_file "$output_file" "$scan_file_path")"
  step_names+=("$name")
  step_codes+=("$rc")
  step_calls+=("$(count_calls "$output_file")")
  step_scans+=("$scan_result")
  step_files+=("$output_file")
  if (( rc != 0 )); then
    echo "STOP: $name failed with exit code $rc; captured output is retained at $output_file."
    print_summary
    return "$rc"
  fi
  return 0
}

if [[ "$MOCK_MODE" == "1" ]]; then
  run_step env-validation "$PYTHON_BIN" -m examples.live_preflight --validate-env-only || exit $?
else
  run_step env-validation "$PYTHON_BIN" -m examples.live_preflight --validate-env-only || exit $?
fi
if [[ "$MOCK_MODE" == "1" ]]; then
  start_mock_server || { echo "STOP: local mock server failed to start."; exit 1; }
  seed_mock_token || { echo "STOP: local mock token setup failed."; exit 1; }
fi
run_step net-watch net-watch || exit $?
run_step live-token-status "$MAKE_BIN" live-token-status || exit $?
status_index=$((${#step_files[@]} - 1))
status_file="${step_files[$status_index]}"
needs_new_token=0
if grep -q '^Token file: missing$' "$status_file" \
  || grep -q '^Cached access token credential binding: unavailable$' "$status_file" \
  || grep -q '^Cached access token matches configured client credentials: no$' "$status_file" \
  || grep -q '^Cached access token: absent$' "$status_file" \
  || grep -q '^Cached access token state: expired$' "$status_file"; then
  needs_new_token=1
fi
minutes_left="$(sed -n 's/^Access token minutes remaining: \([0-9][0-9]*\(\.[0-9]*\)\{0,1\}\)$/\1/p' "$status_file" | tail -n 1)"
if [[ -z "$minutes_left" ]] || awk -v mins="$minutes_left" 'BEGIN {exit !(mins <= 5)}'; then
  needs_new_token=1
fi
if (( needs_new_token == 1 )); then
  if [[ "$MOCK_MODE" == "1" ]]; then
    echo "FAIL: mock token cache unexpectedly stale; refusing to run interactive token setup in --mock mode."
    print_summary
    exit 1
  fi
  printf '\033[1mGenerate a fresh read-scope grant code in the Self Client NOW, then paste it at the hidden prompt\033[0m\n'
  run_step zoho-token || exit $?
  run_step live-token-status-after-exchange "$MAKE_BIN" live-token-status || exit $?
fi
run_step live-preflight "$MAKE_BIN" live-preflight || exit $?
run_step live-smoke "$MAKE_BIN" live-smoke || exit $?
run_step live-probe "$MAKE_BIN" live-probe || exit $?
run_step live-assert "$MAKE_BIN" live-assert || exit $?
print_summary
