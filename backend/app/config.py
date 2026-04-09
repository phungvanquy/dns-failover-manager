from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/dns_failover"
    CLOUDFLARE_API_TOKEN: str = ""
    CLOUDFLARE_BASE_URL: str = "https://api.cloudflare.com/client/v4"
    DEFAULT_CHECK_INTERVAL: int = 30
    FAILURE_THRESHOLD: int = 3
    SUCCESS_THRESHOLD: int = 2
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
