from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FASTFENCE_", extra="forbid")

    root: Path = Field(
        default_factory=lambda: Path.cwd(), description="Repository/config root"
    )
    state: Path | None = Field(
        default=None, description="Private credential and ledger directory"
    )
    ollama_url: str = Field(
        default="http://127.0.0.1:11434", description="Trusted Ollama endpoint"
    )
    kev_url: str = Field(
        default="http://127.0.0.1:8009", description="Trusted Kev endpoint"
    )

    @model_validator(mode="after")
    def resolve_paths(self) -> Self:
        self.root = self.root.resolve()
        self.state = (self.state or self.root / "state").resolve()
        return self

    @property
    def state_path(self) -> Path:
        assert self.state is not None
        return self.state

    @classmethod
    def environment(cls) -> Self:
        return cls()
