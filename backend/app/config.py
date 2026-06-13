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
    WC_WEBHOOK_SECRET: str = ""
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

    # RAG / Vector DB (AI-29)
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "wc_products"
    QDRANT_VECTOR_SIZE: int = 1536
    EMBEDDINGS_PROVIDER: str = "openai"
    EMBEDDINGS_MODEL: str = "text-embedding-3-small"
    EMBEDDINGS_CACHE_TTL: int = 3600
    EMBEDDINGS_BATCH_SIZE: int = 100
    RAG_TOP_K: int = 5
    RAG_MIN_SCORE: float = 0.35
    RAG_TIMEOUT_SEC: float = 2.8
    RAG_LLM_ENABLED: bool = True

    # Auth & rate limiting
    ALLOWED_API_KEYS: list[str] = []
    IP_RATE_LIMIT_PER_MIN: int = 60

    # Admin panel (feature 012)
    ADMIN_PASSWORD_HASH: str = ""
    ADMIN_PASSWORD_SALT: str = ""
    ADMIN_SESSION_TTL: int = 28800  # 8h, deslizante
    ADMIN_SHIPPING_COST_ESTIMATE: int = 12000  # flete estimado COP para margen Dropi

    # MFA del panel (TOTP + respaldo WhatsApp)
    ADMIN_TOTP_SECRET: str = ""  # base32; si vacío, MFA deshabilitado (no enrolado)
    ADMIN_PHONE: str = ""  # E.164 sin '+' (ej. 573166235026) para el código de respaldo

    # Observabilidad IA + bandeja WhatsApp (feature 013)
    # USD por millón de tokens {modelo: [input, output]}; matching por prefijo.
    AI_MODEL_PRICES: str = (
        '{"openai/gpt-4o-mini": [0.15, 0.60],'
        ' "google/gemini-2.0-flash": [0.10, 0.40],'
        ' "anthropic/claude-haiku-4-5": [1.00, 5.00],'
        ' "meta-llama/llama-3.1-8b-instruct": [0.02, 0.03]}'
    )
    WA_HUMAN_PAUSE_HOURS: int = 12  # pausa del bot tras respuesta manual

    # Product Scout — catálogo Dropi (feature 014)
    DROPI_INTEGRATION_KEY: str = ""  # token de integración (Chatbot Agents); catálogo/scout
    DROPI_API_BASE: str = "https://api.dropi.co/integrations"
    # El WAF de Dropi rechaza UAs de CLI/librerías; UA tipo WordPress validado (research R1)
    DROPI_USER_AGENT: str = "WordPress/6.7; https://tiendamagica.shop"
    # Sync de pedidos Dropi → WooCommerce (feature 016).
    # Token de la integración WOOCOMERCE de Dropi (distinto al de Scout). Vacío = sync deshabilitado.
    DROPI_WC_INTEGRATION_KEY: str = ""
    DROPI_ORDERS_FETCH: int = 200  # result_number en /orders/myorders por corrida de sync
    # Si True, además de escribir metadatos transiciona el estado de la orden WC
    # (puede disparar emails/automatizaciones de WooCommerce). False = solo metadatos.
    DROPI_SYNC_WC_STATUS: bool = True
    SCOUT_FREIGHT_COST: int = 12000  # flete estimado COP para margen
    SCOUT_TOP_N: int = 30  # candidatos enviados al scoring IA
    SCOUT_NOVELTY_DAYS: int = 14
    SCOUT_NOVELTY_STOCK: int = 50
    SCOUT_PRICE_MIN: int = 30000  # rango COD atractivo (criterio scoring)
    SCOUT_PRICE_MAX: int = 150000

    # Editor de productos (feature 015)
    # Base pública del backend; WooCommerce descarga los creativos desde aquí.
    PUBLIC_API_BASE: str = "https://api.tiendamagica.shop"
    # Microsoft Clarity: id del proyecto para el mapa de calor (vacío = sin tracking)
    CLARITY_PROJECT_ID: str = ""

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
