from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    APP_NAME: str = "FinPilot AI"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql://finpilot:finpilot_password@localhost:5432/finpilot_db"

    JWT_SECRET: str = "change-this-secret-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:4173"

    AI_PROVIDER: str = "groq"  # groq | openrouter
    AI_MODEL: str = "google/gemma-4-26b-a4b-it:free"
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    DEMO_MODE: bool = False

    MAX_UPLOAD_SIZE_MB: int = 10
    UPLOAD_DIR: str = "./uploads"

    TALLY_ENABLED: bool = False
    TALLY_HOST: str = "localhost"
    TALLY_PORT: int = 9000
    TALLY_CONNECTOR_POLL_INTERVAL: int = 10   # seconds the connector polls for jobs
    TALLY_PAIRING_CODE_TTL_MINUTES: int = 10  # how long a pairing code is valid
    TALLY_HEARTBEAT_TIMEOUT_SECONDS: int = 120  # after this without heartbeat → offline

    @property
    def cors_origins_list(self) -> List[str]:
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        # In development, automatically include common localhost variants
        if self.APP_ENV == "development":
            for port in range(3000, 3010):
                origins.append(f"http://localhost:{port}")
            origins.append("http://localhost:5173")
            origins.append("http://localhost:5174")
        return list(set(origins))

    @property
    def is_demo_mode(self) -> bool:
        return False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
