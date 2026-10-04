from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fastfence.shared.acp import ACPAgentSettings, ACPName
from fastfence.shared.settings.upstream_url import validate_openai_base_url


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FASTFENCE_", extra="forbid")

    root: Path = Field(
        default_factory=lambda: Path.cwd(),
        description="Installation/configuration root",
    )
    state: Path | None = Field(
        default=None,
        description="Legacy private startup identity configuration directory",
    )
    authoring_root: Path | None = Field(
        default=None,
        description="Trusted working directory for the isolated Laya installation",
    )
    identity_config_json: str | None = Field(
        default=None, description="Trusted startup identity records as JSON"
    )
    identity_config_file: Path | None = Field(
        default=None,
        description="Trusted read-only startup identity configuration file",
    )
    identity_max_records: int = Field(
        default=4096,
        ge=1,
        le=65_536,
        description="Maximum startup identities, including administrators; independent of active request capacity",
    )
    identity_max_source_bytes: int = Field(
        default=1_048_576,
        ge=1024,
        le=67_108_864,
        description="Maximum UTF-8 bytes of file or inline startup identity configuration",
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
    model_provider: Literal["ollama", "openai"] = Field(
        default="ollama", description="Protected business model backend"
    )
    openai_base_url: str = Field(
        default="http://127.0.0.1:11434/v1",
        description="Trusted OpenAI-compatible base URL including /v1; HTTPS or loopback HTTP",
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="Server-only upstream bearer credential; independent of gateway caller tokens",
        repr=False,
    )
    acp_agents: dict[ACPName, ACPAgentSettings] = Field(
        default_factory=dict,
        max_length=32,
        description="Trusted ACP agent registry as a JSON object: alias to base_url, agent_name, optional server-only api_key and timeout_seconds",
    )
    secret_plugin_files: list[Path] = Field(
        default_factory=list,
        max_length=8,
        description="Trusted local Python detect-secrets plugin files as a JSON list; loaded at startup, restart after edits",
    )
    secret_plugin_max_file_bytes: int = Field(
        default=65_536,
        ge=1024,
        le=1_048_576,
        description="Maximum bytes read from each trusted secret detector Python file",
    )
    kev_url: str = Field(
        default="http://127.0.0.1:8009", description="Trusted Kev endpoint"
    )
    anonymization_keys_json: SecretStr | None = Field(
        default=None,
        description="Private JSON keyring: key ID to base64-encoded 32-byte key; required for stateless anonymization",
        repr=False,
    )
    anonymization_keys_file: Path | None = Field(
        default=None,
        description="Private JSON keyring file; defaults to state/anonymization-keys.json when present",
    )
    anonymization_key_id: str = Field(
        default="local-v1",
        pattern=r"^[a-zA-Z0-9_-]{1,16}$",
        description="Active key ID for issuing stateless anonymization tokens",
    )
    anonymization_ttl_seconds: int = Field(
        default=1800,
        ge=60,
        le=86400,
        description="Maximum lifetime of reversible text tokens in seconds",
    )
    anonymization_public_key_file: Path | None = Field(
        default=None,
        description="Trusted RSA-3072 public PEM for FFR2 encryption; requires matching private PEM and issuer keyring",
    )
    anonymization_private_key_file: Path | None = Field(
        default=None,
        description="Private RSA-3072 PEM for FFR2 recovery and security reinspection; both RSA paths are required together",
    )

    ocr_python: Path | None = Field(
        default=None, description="Trusted isolated OCR Python interpreter"
    )
    ocr_models: Path | None = Field(
        default=None, description="Trusted local OCR model directory"
    )
    ocr_timeout_seconds: float = Field(
        default=60, ge=1, le=180, description="OCR worker timeout in seconds"
    )
    ocr_max_pages: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum document pages; excess pages are rejected",
    )
    ocr_max_pixels: int = Field(
        default=20_000_000,
        ge=1000,
        le=40_000_000,
        description="Maximum pixels per OCR page",
    )
    ocr_max_total_pixels: int = Field(
        default=80_000_000,
        ge=1000,
        le=160_000_000,
        description="Maximum aggregate pixels per OCR request",
    )

    @field_validator("openai_base_url")
    @classmethod
    def validate_model_url(cls, value: str) -> str:
        return validate_openai_base_url(value)

    @model_validator(mode="after")
    def resolve_paths(self) -> Self:
        self.root = self.root.resolve()
        self.secret_plugin_files = [
            (self.root / path).resolve() for path in self.secret_plugin_files
        ]
        if len(set(self.secret_plugin_files)) != len(self.secret_plugin_files):
            raise ValueError("Duplicate trusted secret detector files")
        self.state = (self.state or self.root / "state").resolve()
        if self.authoring_root is not None:
            self.authoring_root = self.authoring_root.resolve()
        if self.identity_config_file is not None:
            self.identity_config_file = self.identity_config_file.resolve()
        if (self.anonymization_public_key_file is None) != (
            self.anonymization_private_key_file is None
        ):
            raise ValueError(
                "Both anonymization public and private key files are required"
            )
        for name in (
            "anonymization_public_key_file",
            "anonymization_private_key_file",
        ):
            path = getattr(self, name)
            if path is not None:
                setattr(self, name, (self.root / path).resolve())
        ocr_root = self.state_path / "private"
        if (
            self.ocr_python is None
            and (ocr_root / "ocr-env/bin/python").is_file()
        ):
            self.ocr_python = ocr_root / "ocr-env/bin/python"
        if self.ocr_models is None and (ocr_root / "ocr-models").is_dir():
            self.ocr_models = ocr_root / "ocr-models"
        return self

    @property
    def state_path(self) -> Path:
        assert self.state is not None
        return self.state

    @classmethod
    def environment(cls) -> Self:
        return cls(_env_file=".env")  # pyright: ignore[reportCallIssue]
