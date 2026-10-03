from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Shared validation convention for external and internal data models."""

    model_config = ConfigDict(extra="forbid")
