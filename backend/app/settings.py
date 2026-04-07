from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    naver_maps_client_id: str | None = Field(default=None, alias="NAVER_MAPS_CLIENT_ID")
    naver_maps_client_secret: str | None = Field(default=None, alias="NAVER_MAPS_CLIENT_SECRET")
    openai_model: str = Field(default="gpt-5.4-nano", alias="OPENAI_MODEL")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/jeonse_db",
        alias="DATABASE_URL",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        alias="CORS_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
