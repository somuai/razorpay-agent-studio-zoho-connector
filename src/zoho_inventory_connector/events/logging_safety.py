"""Process-wide log redaction and quiet defaults for HTTP libraries."""

from __future__ import annotations

import logging
import re
import traceback
from typing import Any, cast

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?\b(?:authorization|authorization_code|access_token|refresh_token|client_secret|grant_code|code|code_verifier|password)\b[\"']?\s*[:=]\s*[\"']?)([^\"'\s&,;}\]]+)"
)
_ZOHO_AUTH = re.compile(r"(?i)(Zoho-oauthtoken|Bearer)\s+[^\s,;]+")
_ID_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:organization_id|[a-z][a-z0-9_]*_id|record_id)\b\s*[=:]\s*)(?:\"([^\"]*)\"|'([^']*)'|([^\s&,;\]}]+))"
)
_LONG_NUMBER = re.compile(r"(?<![A-Za-z0-9])\d{6,}(?![A-Za-z0-9])")
_FACTORY_INSTALLED = False
_STANDARD_LOG_RECORD_FIELDS = frozenset(
    logging.LogRecord("", logging.INFO, "", 0, "", (), None).__dict__
)


def _last_three(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return f"***{digits[-3:]}" if len(digits) >= 3 else "[ID]"


def mask_identifier(value: Any) -> str:
    """Keep only the final three numeric characters of an identifier."""
    return _last_three(str(value))


def _redact_extra(key: str, value: Any) -> Any:
    lower_key = key.lower()
    if any(marker in lower_key for marker in ("token", "secret", "authorization", "grant_code")):
        return "[REDACTED_SECRET]"
    if lower_key.endswith("_id") or lower_key == "record_id":
        return mask_identifier(value)
    if isinstance(value, dict):
        return {
            str(child_key): _redact_extra(str(child_key), child)
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_extra(key, child) for child in value]
    if isinstance(value, tuple):
        return tuple(_redact_extra(key, child) for child in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    """Mask credentials and long numeric identifiers in arbitrary log text."""
    text = _ZOHO_AUTH.sub(lambda match: f"{match.group(1)} [REDACTED]", value)
    text = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)

    def replace_id(match: re.Match[str]) -> str:
        identifier = next((part for part in match.groups()[1:] if part is not None), "")
        return f"{match.group(1)}{_last_three(identifier)}"

    text = _ID_ASSIGNMENT.sub(replace_id, text)
    return _LONG_NUMBER.sub(lambda match: _last_three(match.group(0)), text)


class RedactionFilter(logging.Filter):
    """Scrub rendered messages and exception text before handlers emit them."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = "[unrenderable log message]"
        record.msg = redact_text(rendered)
        record.args = ()
        if record.exc_info:
            formatted = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = redact_text(formatted)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        for key, value in tuple(record.__dict__.items()):
            if key not in _STANDARD_LOG_RECORD_FIELDS:
                record.__dict__[key] = _redact_extra(key, value)
        return True


def _install_record_factory() -> None:
    """Apply redaction at record creation so propagated/new loggers are covered."""
    global _FACTORY_INSTALLED
    if _FACTORY_INSTALLED:
        return
    current: Any = logging.getLogRecordFactory()

    def safe_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = cast(logging.LogRecord, current(*args, **kwargs))
        RedactionFilter().filter(record)
        return record

    logging.setLogRecordFactory(safe_factory)
    _FACTORY_INSTALLED = True


def configure_secure_logging() -> None:
    """Install global redaction and suppress verbose third-party HTTP URLs."""
    _install_record_factory()
    redactor = RedactionFilter()
    root = logging.getLogger()
    if not any(isinstance(item, RedactionFilter) for item in root.filters):
        root.addFilter(redactor)
    for handler in root.handlers:
        if not any(isinstance(item, RedactionFilter) for item in handler.filters):
            handler.addFilter(redactor)
    connector = logging.getLogger("zoho_connector")
    if not any(isinstance(item, RedactionFilter) for item in connector.filters):
        connector.addFilter(redactor)
    for name in ("httpx", "httpcore", "urllib3", "urllib3.connectionpool"):
        logging.getLogger(name).setLevel(logging.WARNING)
