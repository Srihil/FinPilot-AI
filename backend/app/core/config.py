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

    AI_PROVIDER: str = "demo"  # openrouter | groq | ollama | demo
    AI_MODEL: str = "mistralai/mistral-7b-instruct:free"
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    DEMO_MODE: bool = True

    MAX_UPLOAD_SIZE_MB: int = 10
    UPLOAD_DIR: str = "./uploads"

    TALLY_ENABLED: bool = False
    TALLY_HOST: str = "localhost"
    TALLY_PORT: int = 9000

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
        if self.DEMO_MODE:
            return True
        if self.AI_PROVIDER == "demo":
            return True
        if self.AI_PROVIDER == "openrouter" and not self.OPENROUTER_API_KEY:
            return True
        if self.AI_PROVIDER == "groq" and not self.GROQ_API_KEY:
            return True
        return False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
