from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行配置。真实密钥只从环境变量读取，不写入代码仓库。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_name: str = "智测 ZhiTest"
    env: str = Field(default="development", validation_alias=AliasChoices("ZHITEST_ENV"))
    database_url: str = Field(
        default="postgresql+psycopg://zhitest:zhitest@127.0.0.1:5432/zhitest",
        validation_alias=AliasChoices("DATABASE_URL"),
    )
    auto_bootstrap: bool = Field(default=True, validation_alias=AliasChoices("ZHITEST_AUTO_BOOTSTRAP"))
    admin_username: str = Field(default="admin", validation_alias=AliasChoices("ZHITEST_ADMIN_USERNAME"))
    admin_password: str = Field(default="", validation_alias=AliasChoices("ZHITEST_ADMIN_PASSWORD"))
    admin_display_name: str = Field(
        default="系统管理员",
        validation_alias=AliasChoices("ZHITEST_ADMIN_DISPLAY_NAME"),
    )
    session_ttl_seconds: int = Field(default=7200, validation_alias=AliasChoices("ZHITEST_SESSION_TTL_SECONDS"))
    session_cookie_name: str = "zhitest_session"
    cookie_secure: bool = Field(default=False, validation_alias=AliasChoices("ZHITEST_COOKIE_SECURE"))
    trust_proxy: bool = Field(default=False, validation_alias=AliasChoices("ZHITEST_TRUST_PROXY"))
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias=AliasChoices("ZHITEST_CORS_ORIGINS"),
    )
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("ZHITEST_LOG_LEVEL"))
    target_allowlist: str = Field(
        default="127.0.0.1,localhost,::1",
        validation_alias=AliasChoices("ZHITEST_TARGET_ALLOWLIST"),
    )
    llm_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("ZHITEST_LLM_BASE_URL"),
    )
    llm_model: str = Field(default="deepseek-chat", validation_alias=AliasChoices("ZHITEST_LLM_MODEL"))
    llm_api_key: str = Field(default="", validation_alias=AliasChoices("ZHITEST_LLM_API_KEY"))
    secret_key: str = Field(default="", validation_alias=AliasChoices("ZHITEST_SECRET_KEY"))

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
