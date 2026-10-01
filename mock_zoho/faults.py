"""Fault injection configurations for Mock Zoho Server (FR-9)."""

from dataclasses import dataclass


@dataclass
class FaultConfig:
    """Configurable simulated faults for mock testing."""

    inject_401_expired_token: bool = False
    inject_429_rate_limit: bool = False
    retry_after_seconds: int | None = None
    inject_code_44_block: bool = False
    inject_code_45_quota_exhausted: bool = False
    inject_code_1070_concurrency: bool = False
    inject_500_server_error: bool = False
    inject_latency_seconds: float = 0.0

    def reset(self) -> None:
        self.inject_401_expired_token = False
        self.inject_429_rate_limit = False
        self.retry_after_seconds = None
        self.inject_code_44_block = False
        self.inject_code_45_quota_exhausted = False
        self.inject_code_1070_concurrency = False
        self.inject_500_server_error = False
        self.inject_latency_seconds = 0.0


# Global mock faults controller
faults = FaultConfig()
