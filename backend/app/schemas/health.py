from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


class DependencyStatus(BaseModel):
    status: str  # "ok" | "degraded"
    db: bool
    redis: bool
