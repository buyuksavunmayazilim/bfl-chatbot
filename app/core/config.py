from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "bfl_chatbot"
    postgres_user: str = "bfl_user"
    postgres_password: str = "bfl_pass123"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379

    # Ollama
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: int = 15

    # Aktif embedding modeli ve DB sütunu
    similarity_model: str = "BAAI/bge-m3"
    similarity_column: str = "embedding_bge_1024"  # DB'deki sütun adı

    # Similarity eşikleri
    # bge-m3 Min Score 0.426 → 0.75 güvenli bir başlangıç
    similarity_threshold_high: float = 0.65
    similarity_threshold_low: float = 0.50

    # Llama confidence eşiği
    confidence_threshold: float = 0.60

    # Redis TTL (saniye)
    session_ttl: int = 1800

    # Admin panel kimlik dogrulama (RBAC)
    admin_jwt_secret: str = ""          # bos ise postgres_password'tan turetilir (asagida)
    admin_email: str = ""               # ilk super admin e-postasi (giris e-posta iledir)
    admin_user: str = "admin"           # geriye donuk uyum (e-posta ise kullanilir)
    admin_pass: str = ""                # ilk super admin sifresi (bos ise 'admin123' + uyari)
    admin_token_ttl: int = 86400        # JWT omru (saniye) — 24 saat

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"

    @property
    def admin_secret(self) -> str:
        """JWT imza anahtari. admin_jwt_secret verilmemisse DB sifresinden turetilir
        (restart'lar arasinda stabil). Uretimde ADMIN_JWT_SECRET env ayarlanmasi onerilir."""
        if self.admin_jwt_secret:
            return self.admin_jwt_secret
        import hashlib
        return hashlib.sha256(f"bfl-admin::{self.postgres_password}".encode()).hexdigest()


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()