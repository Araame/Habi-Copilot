from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Habi Agency Copilot"
    app_env: str = "development"
    spring_boot_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8080")
    spring_boot_timeout_seconds: float = Field(default=5, gt=0)
    groq_api_key: SecretStr = SecretStr("")
    copilot_llm_model: str = ""
    copilot_llm_timeout_seconds: float = Field(default=20, gt=0, le=120)
    copilot_max_tool_calls: int = Field(default=5, ge=1, le=5)
    copilot_conversation_ttl_minutes: int = Field(default=30, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
