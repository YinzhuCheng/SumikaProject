from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    tz: str = "Asia/Shanghai"
    admin_token: str = Field(default="dev-admin-token", validation_alias="ADMIN_TOKEN")

    data_dir: Path = Field(default=Path("data"), validation_alias="DATA_DIR")
    assets_dir: Path = Field(default=Path("assets"), validation_alias="ASSETS_DIR")
    persona_config: Path = Field(default=Path("config/persona.yml"), validation_alias="PERSONA_CONFIG")

    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    openrouter_api_key_file: Path | None = Field(
        default=None, validation_alias="OPENROUTER_API_KEY_FILE"
    )
    openrouter_model: str = Field(default="openrouter/free", validation_alias="OPENROUTER_MODEL")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_rpm: int = 15
    openrouter_daily_limit: int = 900
    openrouter_empty_retry: int = 2
    openrouter_reasoning_effort: str = Field(default="xhigh", validation_alias="OPENROUTER_REASONING_EFFORT")
    openrouter_reasoning_exclude: bool = Field(default=True, validation_alias="OPENROUTER_REASONING_EXCLUDE")
    openrouter_reasoning_min_tokens: int = Field(default=1200, validation_alias="OPENROUTER_REASONING_MIN_TOKENS")

    onebot_access_token: str = Field(default="dev-onebot-token", validation_alias="ONEBOT_ACCESS_TOKEN")
    outbound_message_delay_min_seconds: float = Field(default=1.0, validation_alias="OUTBOUND_MESSAGE_DELAY_MIN_SECONDS")
    outbound_message_delay_max_seconds: float = Field(default=5.0, validation_alias="OUTBOUND_MESSAGE_DELAY_MAX_SECONDS")

    egress_interface: str = Field(default="auto", validation_alias="EGRESS_INTERFACE")
    egress_monthly_hard_gib: float = Field(default=20.0, validation_alias="EGRESS_MONTHLY_HARD_GIB")
    egress_monthly_soft_gib: float = Field(default=16.0, validation_alias="EGRESS_MONTHLY_SOFT_GIB")

    proactive_enabled: bool = Field(default=True, validation_alias="PROACTIVE_ENABLED")
    search_enabled: bool = Field(default=True, validation_alias="SEARCH_ENABLED")
    ocr_enabled: bool = Field(default=True, validation_alias="OCR_ENABLED")
    asr_enabled: bool = Field(default=False, validation_alias="ASR_ENABLED")

    advanced_memory_enabled: bool = Field(default=False, validation_alias="ADVANCED_MEMORY_ENABLED")
    memmachine_url: str | None = Field(default=None, validation_alias="MEMMACHINE_URL")
    graphiti_url: str | None = Field(default=None, validation_alias="GRAPHITI_URL")
    cognee_url: str | None = Field(default=None, validation_alias="COGNEE_URL")
    memory_sidecar_timeout_seconds: float = Field(default=3.0, validation_alias="MEMORY_SIDECAR_TIMEOUT_SECONDS")

    @property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    def read_openrouter_key(self) -> str:
        if self.openrouter_api_key:
            return self.openrouter_api_key.strip()
        if self.openrouter_api_key_file and self.openrouter_api_key_file.exists():
            return self.openrouter_api_key_file.read_text(encoding="utf-8").strip()
        return ""


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.assets_dir.mkdir(parents=True, exist_ok=True)
    return settings
