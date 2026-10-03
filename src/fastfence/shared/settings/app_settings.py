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
        default=None,
        description="Legacy private startup identity configuration directory",
    )
    identity_config_json: str | None = Field(
        default=None, description="Trusted startup identity records as JSON"
    )
    identity_config_file: Path | None = Field(
        default=None,
        description="Trusted read-only startup identity configuration file",
    )
    instance_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Trusted instance label; generated once when omitted",
    )
    audit_limit: int = Field(
        default=10_000,
        ge=1,
        le=100_000,
        description="Maximum sanitized audit records retained in memory",
    )
    config_url: str | None = Field(
        default=None,
        description="Trusted HTTP source for coherent policy/feed JSON bundle",
    )
    config_poll_interval: float = Field(
        default=2.0,
        ge=0.1,
        le=300,
        description="Background configuration polling interval in seconds",
    )
    config_fetch_timeout: float = Field(
        default=5.0,
        ge=0.1,
        le=60,
        description="Configuration source fetch timeout in seconds",
    )
    max_config_source_bytes: int = Field(
        default=262_144,
        ge=1024,
        le=2_097_152,
        description="Maximum configuration source size in bytes",
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
        if self.identity_config_file is not None:
            self.identity_config_file = self.identity_config_file.resolve()
        return self

    @property
    def state_path(self) -> Path:
        assert self.state is not None
        return self.state

    @classmethod
    def environment(cls) -> Self:
        return cls()
