from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    data_go_kr_api_key: str | None = Field(default=None, alias="DATA_GO_KR_API_KEY")
    naver_maps_client_id: str | None = Field(default=None, alias="NAVER_MAPS_CLIENT_ID")
    naver_maps_client_secret: str | None = Field(default=None, alias="NAVER_MAPS_CLIENT_SECRET")
    naver_search_client_id: str | None = Field(default=None, alias="NAVER_SEARCH_CLIENT_ID")
    naver_search_client_secret: str | None = Field(default=None, alias="NAVER_SEARCH_CLIENT_SECRET")
    openai_model: str = Field(default="gpt-4.1-nano", alias="OPENAI_MODEL")
    vector_db_path: str = Field(default="vectorDB/laws_faiss", alias="VECTOR_DB_PATH")
    vector_db_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="VECTOR_DB_EMBEDDING_MODEL",
    )
    vector_db_top_k: int = Field(default=4, alias="VECTOR_DB_TOP_K")
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
