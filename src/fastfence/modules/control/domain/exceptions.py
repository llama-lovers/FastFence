class BudgetExceededError(Exception):
    """Atomic reservation would exceed a configured resource allocation."""


class ResourceDeniedError(Exception):
    """The verified principal cannot access the requested tenant resource."""


class ModelUnavailableError(Exception):
    """Model provider failed; its raw error must not be sent to callers."""


class ModelCapacityExceededError(ModelUnavailableError):
    """Local bounded model admission rejected work before transport execution."""


class ToolCapacityExceededError(Exception):
    """Local bounded tool admission rejected work before transport execution."""


class RejectedError(Exception):
    def __init__(self, reason: str, findings: list[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.findings = findings or []


class RequestQueueError(Exception):
    """Bounded local request waiting ended before any execution reservation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
