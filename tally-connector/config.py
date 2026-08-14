"""
Connector configuration — reads from .env file or environment variables.
Works both as a plain Python script and as a PyInstaller .exe bundle.
"""
import os
import sys
from pathlib import Path


def _base_dir() -> Path:
    """Return the directory containing the .exe (or the script directory)."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller bundle — use directory of the .exe
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR = _base_dir()

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


class Config:
    # FinPilot cloud API — hardcoded production URL, overridable via .env
    FINPILOT_API_URL: str = os.getenv("FINPILOT_API_URL", "https://finpilot-backend-w1im.onrender.com")
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
