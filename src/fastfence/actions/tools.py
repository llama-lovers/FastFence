from __future__ import annotations

import asyncio
from typing import Any

from pydantic import Field

from fastfence.core.schema import Identity, StrictModel


class SearchArgs(StrictModel):
    query: str = Field(min_length=1, max_length=8192)


class MemoryArgs(StrictModel):
    resource: str = Field(pattern=r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$")


class ContactArgs(StrictModel):
    report: str = Field(default="quarterly", pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class PaymentArgs(StrictModel):
    amount: int = Field(ge=1, le=10_000)
    recipient: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class ResourceDenied(Exception):
    pass


class DemoTools:
    """Simulated business backend; every invocation uses real gateway controls."""

    schemas = {
        "knowledge.search": SearchArgs,
        "memory.read": MemoryArgs,
        "report.contact": ContactArgs,
        "payments.prepare": PaymentArgs,
    }

    def validate(self, tool: str, arguments: dict[str, Any], identity: Identity) -> dict:
        validated = self.schemas[tool].model_validate(arguments).model_dump()
        if tool == "memory.read" and not validated["resource"].startswith(identity.tenant + "/"):
            raise ResourceDenied("cross_tenant_resource")
        return validated

    async def call(self, tool: str, arguments: dict, identity: Identity) -> dict:
        await asyncio.sleep(0.015)
        if tool == "knowledge.search":
            return {
                "source": "SIMULATED internal knowledge",
                "tenant": identity.tenant,
                "answer": f"Approved internal summary for: {arguments['query']}",
            }
        if tool == "memory.read":
            return {
                "source": "SIMULATED tenant memory",
                "resource": arguments["resource"],
                "content": "Quarterly forecast: revenue up 8%; internal planning only.",
            }
        if tool == "report.contact":
            return {
                "source": "SIMULATED business report",
                "owner": "anna@example.org",
                "api_key": "sk-demoOnlySecret123456789",
                "summary": "Report is ready.",
            }
        if tool == "payments.prepare":
            return {
                "source": "SIMULATED payment preparation",
                "status": "prepared",
                "amount": arguments["amount"],
                "recipient": arguments["recipient"],
                "real_payment_sent": False,
            }
        raise ValueError("Unknown tool")
