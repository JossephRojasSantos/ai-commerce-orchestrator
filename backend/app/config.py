from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_VERSION: str = "0.1.0"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:change_me@db:5432/ai_commerce"
    REDIS_URL: str = "redis://redis:6379/0"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    METRICS_ENABLED: bool = True

    # WooCommerce
    WC_BASE_URL: str = "https://tiendamagica.shop/wp-json/wc/v3"
    WC_CONSUMER_KEY: str = ""
    WC_CONSUMER_SECRET: str = ""
    WC_TIMEOUT: float = 10.0
    WC_MAX_RETRIES: int = 3
    WC_CACHE_TTL_PRODUCTS: int = 300
    WC_CACHE_TTL_ORDERS: int = 60

    # Chat
    CHAT_SESSION_TTL: int = 3600
    CHAT_MAX_HISTORY: int = 50
    CHAT_RATE_LIMIT_PER_MIN: int = 30
    CHAT_ALLOWED_ORIGINS: list[str] = ["https://tiendamagica.shop", "http://localhost:3000"]

    # WhatsApp Cloud API (Meta)
    WA_PHONE_ID: str = ""
    WA_SANDBOX_PHONE_ID: str = ""
    WA_ACCESS_TOKEN: str = ""
    WA_WEBHOOK_VERIFY_TOKEN: str = ""
    WA_APP_SECRET: str = ""
    WA_API_VERSION: str = "v18.0"
    WA_RATE_LIMIT_PER_HOUR: int = 10

    # LLM
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://openrouter.ai/api/v1"
    LLM_MODEL_CHAT: str = "openai/gpt-4o-mini"
    LLM_MODEL_ROUTER: str = "google/gemini-2.0-flash"
    LLM_MODEL_WHATSAPP: str = "openai/gpt-4o-mini"
    LLM_FALLBACK_CHAT: str = "anthropic/claude-haiku-4-5"
    LLM_FALLBACK_ROUTER: str = "meta-llama/llama-3.1-8b-instruct"
    LLM_TIMEOUT: float = 30.0
    OPENROUTER_REFERER: str = "https://tiendamagica.shop"
    OPENROUTER_APP_NAME: str = "Tienda Magica"

    # Orchestrator
    ORCHESTRATOR_AGENT_TIMEOUT: float = 15.0
    ORCHESTRATOR_CIRCUIT_BREAKER_THRESHOLD: int = 3
    ORCHESTRATOR_RATE_LIMIT_PER_MIN: int = 20
    INTENT_CACHE_TTL: int = 3600

    # Auth & rate limiting
    ALLOWED_API_KEYS: list[str] = []
    IP_RATE_LIMIT_PER_MIN: int = 60

    @property
    def WA_API_BASE(self) -> str:
        return f"https://graph.facebook.com/{self.WA_API_VERSION}"

    @property
    def WA_ACTIVE_PHONE_ID(self) -> str:
        if self.APP_ENV != "production" and self.WA_SANDBOX_PHONE_ID:
            return self.WA_SANDBOX_PHONE_ID
        return self.WA_PHONE_ID

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
