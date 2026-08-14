"""
Tally Integration endpoint.
The application uses a FinanceDataProvider abstraction.
TallyFinanceProvider can be swapped in without changing business logic.
"""
from fastapi import APIRouter, Depends, HTTPException
from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User
from app.core.config import settings

router = APIRouter(prefix="/tally", tags=["tally"])


@router.get("/status")
def get_tally_status(current_user: User = Depends(get_current_user)):
    return {
        "enabled": settings.TALLY_ENABLED,
        "host": settings.TALLY_HOST if settings.TALLY_ENABLED else None,
        "port": settings.TALLY_PORT if settings.TALLY_ENABLED else None,
        "connected": False,  # Would test connection if enabled
        "message": (
            "Tally integration is available but not configured. "
            "Set TALLY_ENABLED=true and configure TALLY_HOST/TALLY_PORT in your .env to enable."
        ),
        "documentation": {
            "overview": "FinPilot AI uses a FinanceDataProvider abstraction layer.",
            "default_provider": "PostgresFinanceProvider (active)",
            "optional_provider": "TallyFinanceProvider (not yet connected)",
            "setup_steps": [
                "1. Enable XML bridge in TallyPrime: Gateway of Tally → F12 Configuration → Enable ODBC",
                "2. Set TALLY_ENABLED=true in .env",
                "3. Set TALLY_HOST (default: localhost) and TALLY_PORT (default: 9000)",
                "4. Restart the backend",
            ],
            "architecture": "App → FinanceDataProvider (abstract) → PostgresFinanceProvider OR TallyFinanceProvider → Data",
        }
    }


@router.get("/test-connection")
def test_tally_connection(current_user: User = Depends(require_admin)):
    if not settings.TALLY_ENABLED:
        raise HTTPException(status_code=400, detail="Tally integration is not enabled")

    import httpx
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"http://{settings.TALLY_HOST}:{settings.TALLY_PORT}")
            return {"connected": True, "status_code": resp.status_code}
    except Exception as e:
        return {"connected": False, "error": str(e)}
