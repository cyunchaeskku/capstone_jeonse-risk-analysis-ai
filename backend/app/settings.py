from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    data_go_kr_api_key: str | None = Field(default=None, alias="DATA_GO_KR_API_KEY")
    naver_maps_client_id: str | None = Field(default=None, alias="NAVER_MAPS_CLIENT_ID")
    naver_maps_client_secret: str | None = Field(default=None, alias="NAVER_MAPS_CLIENT_SECRET")
    naver_search_client_id: str | None = Field(default=None, alias="NAVER_SEARCH_CLIENT_ID")
    naver_search_client_secret: str | None = Field(default=None, alias="NAVER_SEARCH_CLIENT_SECRET")
    vworld_api_key: str | None = Field(default=None, alias="VWORLD_API_KEY")
    # VWorld는 인증키 발급 시 등록한 서비스URL을 domain 파라미터로 함께 보내야 한다.
    # 빠뜨리면 키가 맞아도 INCORRECT_KEY로 거부된다.
    vworld_api_domain: str = Field(default="http://localhost:5173", alias="VWORLD_API_DOMAIN")
    openai_model: str = Field(default="gpt-4.1-nano", alias="OPENAI_MODEL")
    # 건축물대장은 이미지 스캔본이라 비전 모델로 읽는다. nano는 표 칸 대응을 자주 틀리고
    # gpt-4.1은 오히려 없는 건물명·지번을 지어내서, 실측 결과 mini가 가장 정확했다.
    openai_vision_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_VISION_MODEL")
    vector_db_path: str = Field(default="vectorDB/laws_faiss", alias="VECTOR_DB_PATH")
    vector_db_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="VECTOR_DB_EMBEDDING_MODEL",
    )
    vector_db_top_k: int = Field(default=4, alias="VECTOR_DB_TOP_K")
    database_url: str = Field(alias="DATABASE_URL")
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
