from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:change_me@db:5432/ai_commerce"
    REDIS_URL: str = "redis://redis:6379/0"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    LOG_LEVEL: str = "INFO"

    # WooCommerce
    WC_BASE_URL: str = "https://tiendamagica.shop/wp-json/wc/v3"
    WC_CONSUMER_KEY: str = ""
    WC_CONSUMER_SECRET: str = ""
    WC_TIMEOUT: float = 10.0
    WC_MAX_RETRIES: int = 3
    WC_CACHE_TTL_PRODUCTS: int = 300
    WC_CACHE_TTL_ORDERS: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
