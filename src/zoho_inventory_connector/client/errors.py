"""Typed error hierarchy for Zoho Inventory Connector (FR-2.2, FR-7)."""


class ConnectorError(Exception):
    """Base exception for all Zoho Inventory Connector errors."""

    def __init__(
        self,
        message: str,
        agent_guidance: str,
        retryable: bool = False,
        retry_after: float | None = None,
        zoho_code: int | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.agent_guidance = agent_guidance
        self.retryable = retryable
        self.retry_after = retry_after
        self.zoho_code = zoho_code
        self.http_status = http_status

    def to_dict(self) -> dict[str, object]:
        """Format error as self-explaining dictionary for LLM consumption (FR-7)."""
        data: dict[str, object] = {
            "error": self.__class__.__name__,
            "message": self.message,
            "agent_guidance": self.agent_guidance,
            "retryable": self.retryable,
        }
        if self.retry_after is not None:
            data["retry_after_seconds"] = self.retry_after
        if self.zoho_code is not None:
            data["zoho_code"] = self.zoho_code
        if self.http_status is not None:
            data["http_status"] = self.http_status
        diagnostic = getattr(self, "transport_diagnostic", None)
        if diagnostic is not None:
            data["transport_diagnostic"] = diagnostic
        return data


class AuthError(ConnectorError):
    """Authentication or OAuth token authorization failed (FR-1, FR-2.3)."""

    def __init__(
        self,
        message: str = "Zoho OAuth authentication failed.",
        agent_guidance: str = "Authentication with Zoho failed; ask the merchant or user to reconnect credentials.",
        http_status: int = 401,
        zoho_code: int | None = None,
        transport_diagnostic: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            agent_guidance=agent_guidance,
            retryable=False,
            http_status=http_status,
            zoho_code=zoho_code,
        )
        self.transport_diagnostic = transport_diagnostic


class RateLimitError(ConnectorError):
    """Rate limit exceeded: per-minute bucket (429) or concurrency limit (1070) (FR-3.3)."""

    def __init__(
        self,
        kind: str = "per_minute",
        retry_after: float | None = 1.0,
        message: str | None = None,
        agent_guidance: str | None = None,
        http_status: int = 429,
        zoho_code: int | None = None,
    ) -> None:
        self.kind = kind
        msg = message or f"Zoho API rate limit reached ({kind})."
        guidance = agent_guidance or (
            f"Rate limited by Zoho ({kind}); backoff and retry after {retry_after or 1.0}s."
            if kind == "per_minute"
            else "Too many concurrent requests to Zoho; reduce parallelism and retry shortly."
        )
        super().__init__(
            message=msg,
            agent_guidance=guidance,
            retryable=True,
            retry_after=retry_after,
            http_status=http_status,
            zoho_code=zoho_code,
        )


class QuotaExhaustedError(ConnectorError):
    """Daily API quota exceeded (Zoho Error Code 45) (FR-3.4).

    CRITICAL RULE: Never retry this error. Hard stop until next calendar day.
    """

    def __init__(
        self,
        message: str = "Zoho daily API quota is exhausted for this organization (Zoho code 45).",
        agent_guidance: str = (
            "Zoho daily API quota is exhausted for this organization. Do not retry today. "
            "Tell the user inventory data is temporarily unavailable; use cached data only if as_of "
            "is within the allowed window."
        ),
        zoho_code: int = 45,
        http_status: int = 429,
    ) -> None:
        super().__init__(
            message=message,
            agent_guidance=agent_guidance,
            retryable=False,
            retry_after=None,
            zoho_code=zoho_code,
            http_status=http_status,
        )


class CircuitOpenError(ConnectorError):
    """Circuit breaker is open due to organization block (Code 44) or severe upstream throttling (FR-3.5)."""

    def __init__(
        self,
        cooldown_remaining: float,
        message: str | None = None,
        agent_guidance: str | None = None,
        zoho_code: int | None = 44,
    ) -> None:
        self.cooldown_remaining = cooldown_remaining
        msg = (
            message
            or f"Circuit breaker open: Zoho requests temporarily blocked. Cooldown: {cooldown_remaining:.1f}s."
        )
        guidance = agent_guidance or (
            f"Zoho temporarily blocked requests for this organization (Code 44); "
            f"fail fast and do not send requests for the next {cooldown_remaining:.0f} seconds."
        )
        super().__init__(
            message=msg,
            agent_guidance=guidance,
            retryable=False,
            retry_after=cooldown_remaining,
            zoho_code=zoho_code,
            http_status=429,
        )


class NotFoundError(ConnectorError):
    """Requested resource (item, sales order, package) does not exist (FR-2.2)."""

    def __init__(
        self,
        resource: str,
        identifier: str,
        message: str | None = None,
        agent_guidance: str | None = None,
    ) -> None:
        msg = message or f"Zoho {resource} with ID '{identifier}' not found."
        guidance = (
            agent_guidance
            or f"No such {resource} found in Zoho; verify the identifier and do not guess data."
        )
        super().__init__(
            message=msg,
            agent_guidance=guidance,
            retryable=False,
            http_status=404,
        )


class UpstreamError(ConnectorError):
    """Upstream 5xx error or unrecoverable network failure (FR-2.4)."""

    def __init__(
        self,
        message: str = "Zoho API upstream error or network connection failure.",
        agent_guidance: str = "Zoho service is temporarily unavailable; do not guess data. Try again later.",
        http_status: int | None = 500,
        zoho_code: int | None = None,
        transport_diagnostic: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            agent_guidance=agent_guidance,
            retryable=True,
            retry_after=2.0,
            http_status=http_status,
            zoho_code=zoho_code,
        )
        self.transport_diagnostic = transport_diagnostic


class InvalidResponseError(ConnectorError):
    """Zoho returned a successful response with data that cannot be projected safely."""

    def __init__(self, field: str) -> None:
        super().__init__(
            message=f"Zoho returned an invalid value for projected field '{field}'.",
            agent_guidance="Do not use this result. Verify the Zoho response mapping and retry after it is corrected.",
            retryable=False,
            http_status=200,
        )


class AuditSinkError(ConnectorError):
    """The invocation audit record could not be persisted; fail the tool closed."""

    def __init__(self, tool: str, request_id: str) -> None:
        self.tool = tool
        self.request_id = request_id
        super().__init__(
            message="The tool audit record could not be saved, so this request was not run.",
            agent_guidance="Ask the operator to restore the audit log destination before retrying.",
            retryable=False,
        )


class InputValidationError(ConnectorError):
    """Tool input failed validation rules (FR-5.5, FR-13).

    Protects upstream queries against injection, illegal characters, and out-of-bound arguments.
    """

    def __init__(
        self,
        field: str,
        value: str,
        reason: str,
        agent_guidance: str | None = None,
    ) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        msg = f"Invalid input for field '{field}': {reason} (received '{value}')."
        guidance = agent_guidance or (
            f"The value for '{field}' was rejected: {reason}. "
            "Correct the input format and retry without special query operators or excess characters."
        )
        super().__init__(
            message=msg,
            agent_guidance=guidance,
            retryable=False,
            http_status=400,
        )
