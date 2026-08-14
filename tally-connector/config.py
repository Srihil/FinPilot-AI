"""
Connector configuration — reads from .env file or environment variables.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


class Config:
    # FinPilot cloud API
    FINPILOT_API_URL: str = os.getenv("FINPILOT_API_URL", "https://your-backend.onrender.com")
    CONNECTOR_TOKEN: str = os.getenv("CONNECTOR_TOKEN", "")

    # TallyPrime
    TALLY_HOST: str = os.getenv("TALLY_HOST", "localhost")
    TALLY_PORT: int = int(os.getenv("TALLY_PORT", "9000"))

    # Behaviour
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
    HEARTBEAT_INTERVAL_SECONDS: int = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "30"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.CONNECTOR_TOKEN and cls.FINPILOT_API_URL)


config = Config()
