class BudgetExceededError(Exception):
    """Atomic reservation would exceed a configured resource allocation."""


class ResourceDeniedError(Exception):
    """The verified principal cannot access the requested tenant resource."""


class ModelUnavailableError(Exception):
    """Model provider failed; its raw error must not be sent to callers."""


class RejectedError(Exception):
    def __init__(self, reason: str, findings: list[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.findings = findings or []
