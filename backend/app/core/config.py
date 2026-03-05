from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "production", "testing"] = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_TITLE: str = "SkillNexus API"
    APP_DESCRIPTION: str = "AI-Powered Enterprise Learning & Development Platform"
    APP_VERSION: str = "1.0.0"

    # ── Database ───────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://skillnexus:skillnexus_secret@localhost:5432/skillnexus_db"
    )
    # Sync URL for Alembic migrations
    DATABASE_URL_SYNC: str = Field(
        default="postgresql+psycopg2://skillnexus:skillnexus_secret@localhost:5432/skillnexus_db"
    )

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT Authentication ─────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_REFRESH_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── LLM Provider ──────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["gemini", "groq", "openai"] = "gemini"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"

    # Groq
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # ── File Upload ────────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 10

    # ── CORS ───────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # ── Gamification ───────────────────────────────────────────────────────────
    XP_NODE_COMPLETE: int = 50
    XP_STREAK_BONUS: int = 100
    XP_LOGIN: int = 5
    STREAK_THRESHOLD_DAYS: int = 7

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must be set")
        return v

    @model_validator(mode="after")
    def validate_llm_keys(self) -> "Settings":
        provider = self.LLM_PROVIDER
        if provider == "gemini" and not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY must be set when LLM_PROVIDER=gemini")
        if provider == "groq" and not self.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY must be set when LLM_PROVIDER=groq")
        if provider == "openai" and not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY must be set when LLM_PROVIDER=openai")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
