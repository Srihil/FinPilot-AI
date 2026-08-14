"""
Tally Integration endpoints.

Two authentication contexts:
  1. User-facing (JWT): pairing, status, sync, disconnect, jobs, activity
  2. Connector-facing (bearer token): register, heartbeat, job poll, job result
"""
import secrets
import string
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.core.config import settings
from app.core.security import pwd_context
from app.db.base import get_db
from app.models.audit_log import AuditAction
from app.models.approval import Approval, ApprovalStatus
from app.models.tally_connector import TallyConnector, TallyPairingCode, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, JobStatus, TallyJobOperation, WRITE_OPERATIONS
from app.models.user import User
from app.services.audit_service import audit_service

router = APIRouter(prefix="/tally", tags=["tally"])

connector_security = HTTPBearer(auto_error=False)

MAX_RETRY = 3


# ─── helpers ────────────────────────────────────────────────────────────────

def _gen_pairing_code(length: int = 9) -> str:
    alphabet = string.ascii_uppercase + string.digits
    # format: XXXX-XXXX
    raw = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{raw[:4]}-{raw[4:]}"


def _gen_connector_token() -> str:
    return secrets.token_urlsafe(48)


def _hash_token(token: str) -> str:
    return pwd_context.hash(token)


def _verify_token(token: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(token, hashed)
    except Exception:
        return False


def _resolve_connector(
    credentials: HTTPAuthorizationCredentials,
    db: Session,
) -> TallyConnector:
    if not credentials:
        raise HTTPException(status_code=401, detail="Connector token required")
    token = credentials.credentials
    # iterate active connectors — token is never stored in plain text
    active = db.query(TallyConnector).filter(
        TallyConnector.status == ConnectorStatus.ACTIVE
    ).all()
    for c in active:
        if _verify_token(token, c.token_hash):
            return c
    raise HTTPException(status_code=401, detail="Invalid or revoked connector token")


def _connector_online(c: TallyConnector) -> bool:
    if not c.last_heartbeat:
        return False
    delta = (datetime.now(timezone.utc) - c.last_heartbeat).total_seconds()
    return delta < settings.TALLY_HEARTBEAT_TIMEOUT_SECONDS


# ─── Pydantic schemas ───────────────────────────────────────────────────────

class PairingGenerateResponse(BaseModel):
    code: str
    expires_in_minutes: int
    expires_at: str


class ConnectorRegisterRequest(BaseModel):
    pairing_code: str
    connector_name: Optional[str] = "FinPilot Connector"
    device_name: Optional[str] = None


class ConnectorRegisterResponse(BaseModel):
    connector_id: str
    token: str
    poll_interval_seconds: int
    message: str


class HeartbeatRequest(BaseModel):
    tally_reachable: bool
    tally_company_name: Optional[str] = None
    tally_host: Optional[str] = None
    tally_port: Optional[int] = None


class JobResultRequest(BaseModel):
    status: str           # "SUCCESS" | "FAILED"
    result: Optional[dict] = None
    error_message: Optional[str] = None


class CreateJobRequest(BaseModel):
    operation: str
    payload: Optional[dict] = None
    approval_id: Optional[str] = None
    idempotency_key: Optional[str] = None


# ─── User-facing: status ────────────────────────────────────────────────────

@router.get("/status")
def get_tally_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).order_by(TallyConnector.created_at.desc()).first()

    if not connector:
        return {
            "connected": False,
            "connector": None,
            "tally_online": False,
            "message": "No connector paired. Generate a pairing code to connect.",
        }

    online = _connector_online(connector)
    return {
        "connected": True,
        "connector": {
            "id": str(connector.id),
            "name": connector.connector_name,
            "device": connector.device_name,
            "status": connector.status.value,
            "tally_company": connector.tally_company_name,
            "tally_host": connector.tally_host,
            "tally_port": connector.tally_port,
            "last_heartbeat": connector.last_heartbeat.isoformat() if connector.last_heartbeat else None,
            "last_sync_at": connector.last_sync_at.isoformat() if connector.last_sync_at else None,
            "paired_at": connector.created_at.isoformat(),
        },
        "tally_online": online,
        "message": "Connector active — TallyPrime reachable" if online else "Connector registered but TallyPrime is offline or heartbeat timed out",
    }


# ─── User-facing: pairing ───────────────────────────────────────────────────

@router.post("/pairing/generate")
def generate_pairing_code(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Expire any old unused codes for this company
    db.query(TallyPairingCode).filter(
        TallyPairingCode.company_id == current_user.company_id,
        TallyPairingCode.is_used == False,
    ).delete()

    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.TALLY_PAIRING_CODE_TTL_MINUTES)
    code = _gen_pairing_code()
    pc = TallyPairingCode(
        company_id=current_user.company_id,
        code=code,
        created_by=current_user.id,
        expires_at=expires,
    )
    db.add(pc)
    db.commit()

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.SETTINGS_CHANGE,
        entity_type="tally_pairing",
        description="Tally connector pairing code generated",
    )

    return PairingGenerateResponse(
        code=code,
        expires_in_minutes=settings.TALLY_PAIRING_CODE_TTL_MINUTES,
        expires_at=expires.isoformat(),
    )


# ─── User-facing: disconnect ────────────────────────────────────────────────

@router.post("/disconnect")
def disconnect_connector(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if not connector:
        raise HTTPException(status_code=404, detail="No active connector found")

    connector.status = ConnectorStatus.REVOKED
    connector.revoked_at = datetime.now(timezone.utc)
    db.commit()

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.SETTINGS_CHANGE,
        entity_type="tally_connector",
        entity_id=connector.id,
        description=f"Tally connector '{connector.connector_name}' disconnected",
    )
    return {"message": "Connector disconnected successfully"}


# ─── User-facing: sync ──────────────────────────────────────────────────────

@router.post("/sync")
def trigger_sync(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if not connector:
        raise HTTPException(status_code=400, detail="No active connector. Pair a connector first.")

    if not _connector_online(connector):
        raise HTTPException(status_code=400, detail="Connector is offline. Start the FinPilot Tally Connector on your PC.")

    idem_key = f"sync-{current_user.company_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    existing = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.idempotency_key == idem_key
    ).first()
    if existing:
        return {"message": "Sync already queued", "job_id": str(existing.id)}

    job = TallyIntegrationJob(
        company_id=current_user.company_id,
        connector_id=connector.id,
        created_by=current_user.id,
        operation=TallyJobOperation.SYNC_FULL,
        payload={},
        status=JobStatus.PENDING,
        idempotency_key=idem_key,
    )
    db.add(job)
    db.commit()

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.INTEGRATION_SYNC,
        entity_type="tally_sync",
        entity_id=job.id,
        description="Tally full sync triggered",
    )
    return {"message": "Sync job queued", "job_id": str(job.id)}


# ─── User-facing: activity ──────────────────────────────────────────────────

@router.get("/activity")
def get_activity(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jobs = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.company_id == current_user.company_id,
    ).order_by(TallyIntegrationJob.created_at.desc()).limit(limit).all()

    return {
        "items": [
            {
                "id": str(j.id),
                "operation": j.operation.value,
                "status": j.status.value,
                "created_at": j.created_at.isoformat(),
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                "error_message": j.error_message,
                "retry_count": j.retry_count,
            }
            for j in jobs
        ]
    }


# ─── User-facing: create a Tally write job (requires approved approval) ─────

@router.post("/jobs")
def create_tally_job(
    body: CreateJobRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        operation = TallyJobOperation(body.operation)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown operation: {body.operation}")

    if operation in WRITE_OPERATIONS:
        if not body.approval_id:
            raise HTTPException(status_code=400, detail="Write operations require an approved approval_id")
        approval = db.query(Approval).filter(
            Approval.id == uuid.UUID(body.approval_id),
            Approval.company_id == current_user.company_id,
            Approval.status == ApprovalStatus.APPROVED,
        ).first()
        if not approval:
            raise HTTPException(status_code=403, detail="No approved approval found for this operation")

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if not connector:
        raise HTTPException(status_code=400, detail="No active connector")

    idem_key = body.idempotency_key or f"job-{current_user.company_id}-{operation.value}-{secrets.token_hex(8)}"
    existing = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.idempotency_key == idem_key
    ).first()
    if existing:
        return {"message": "Job already exists", "job_id": str(existing.id), "status": existing.status.value}

    job = TallyIntegrationJob(
        company_id=current_user.company_id,
        connector_id=connector.id,
        created_by=current_user.id,
        approval_id=uuid.UUID(body.approval_id) if body.approval_id else None,
        operation=operation,
        payload=body.payload or {},
        status=JobStatus.PENDING,
        idempotency_key=idem_key,
    )
    db.add(job)
    db.commit()

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.INTEGRATION_SYNC,
        entity_type="tally_job",
        entity_id=job.id,
        description=f"Tally job created: {operation.value}",
    )
    return {"message": "Job queued", "job_id": str(job.id)}


# ─── User-facing: get single job status ─────────────────────────────────────

@router.get("/jobs/{job_id}")
def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.id == uuid.UUID(job_id),
        TallyIntegrationJob.company_id == current_user.company_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": str(job.id),
        "operation": job.operation.value,
        "status": job.status.value,
        "payload": job.payload,
        "result": job.result,
        "error_message": job.error_message,
        "retry_count": job.retry_count,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


# ─── Connector-facing: register ─────────────────────────────────────────────

@router.post("/connector/register", response_model=ConnectorRegisterResponse)
def register_connector(
    body: ConnectorRegisterRequest,
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    pc = db.query(TallyPairingCode).filter(
        TallyPairingCode.code == body.pairing_code.strip().upper(),
        TallyPairingCode.is_used == False,
        TallyPairingCode.expires_at > now,
    ).first()
    if not pc:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")

    # Revoke any existing active connector for this company
    db.query(TallyConnector).filter(
        TallyConnector.company_id == pc.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).update({"status": ConnectorStatus.REVOKED, "revoked_at": now})

    raw_token = _gen_connector_token()
    connector = TallyConnector(
        company_id=pc.company_id,
        connector_name=body.connector_name,
        device_name=body.device_name,
        token_hash=_hash_token(raw_token),
        status=ConnectorStatus.ACTIVE,
    )
    db.add(connector)

    pc.is_used = True
    pc.used_at = now
    db.commit()
    db.refresh(connector)

    audit_service.log(
        db, pc.company_id, None,
        AuditAction.SETTINGS_CHANGE,
        entity_type="tally_connector",
        entity_id=connector.id,
        description=f"Tally connector registered: {body.connector_name} on {body.device_name}",
    )

    return ConnectorRegisterResponse(
        connector_id=str(connector.id),
        token=raw_token,
        poll_interval_seconds=settings.TALLY_CONNECTOR_POLL_INTERVAL,
        message=f"Connector registered. Poll every {settings.TALLY_CONNECTOR_POLL_INTERVAL}s for jobs.",
    )


# ─── Connector-facing: heartbeat ────────────────────────────────────────────

@router.post("/connector/heartbeat")
def connector_heartbeat(
    body: HeartbeatRequest,
    credentials: HTTPAuthorizationCredentials = Depends(connector_security),
    db: Session = Depends(get_db),
):
    connector = _resolve_connector(credentials, db)
    connector.last_heartbeat = datetime.now(timezone.utc)
    if body.tally_company_name:
        connector.tally_company_name = body.tally_company_name
    if body.tally_host:
        connector.tally_host = body.tally_host
    if body.tally_port:
        connector.tally_port = body.tally_port
    db.commit()
    return {"ok": True, "poll_interval_seconds": settings.TALLY_CONNECTOR_POLL_INTERVAL}


# ─── Connector-facing: poll jobs ────────────────────────────────────────────

@router.get("/connector/jobs")
def poll_jobs(
    credentials: HTTPAuthorizationCredentials = Depends(connector_security),
    db: Session = Depends(get_db),
):
    connector = _resolve_connector(credentials, db)

    # Update heartbeat opportunistically
    connector.last_heartbeat = datetime.now(timezone.utc)

    jobs = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.company_id == connector.company_id,
        TallyIntegrationJob.connector_id == connector.id,
        TallyIntegrationJob.status.in_([JobStatus.PENDING, JobStatus.RETRYING]),
    ).order_by(TallyIntegrationJob.created_at).limit(5).all()

    # Mark as CLAIMED
    for j in jobs:
        j.status = JobStatus.CLAIMED
        j.claimed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "jobs": [
            {
                "id": str(j.id),
                "operation": j.operation.value,
                "payload": j.payload,
                "idempotency_key": j.idempotency_key,
            }
            for j in jobs
        ]
    }


# ─── Connector-facing: submit job result ────────────────────────────────────

@router.post("/connector/jobs/{job_id}/result")
def submit_job_result(
    job_id: str,
    body: JobResultRequest,
    credentials: HTTPAuthorizationCredentials = Depends(connector_security),
    db: Session = Depends(get_db),
):
    connector = _resolve_connector(credentials, db)

    job = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.id == uuid.UUID(job_id),
        TallyIntegrationJob.company_id == connector.company_id,
        TallyIntegrationJob.connector_id == connector.id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if body.status == "SUCCESS":
        job.status = JobStatus.SUCCESS
        job.result = body.result
        job.error_message = None

        if job.operation in (TallyJobOperation.SYNC_FULL, TallyJobOperation.SYNC_PARTIAL):
            connector.last_sync_at = datetime.now(timezone.utc)
    elif body.status == "FAILED":
        job.retry_count = (job.retry_count or 0) + 1
        job.error_message = body.error_message
        if job.retry_count >= MAX_RETRY:
            job.status = JobStatus.FAILED
        else:
            job.status = JobStatus.RETRYING
    else:
        raise HTTPException(status_code=400, detail="status must be SUCCESS or FAILED")

    job.completed_at = datetime.now(timezone.utc)
    db.commit()

    audit_service.log(
        db, job.company_id, None,
        AuditAction.INTEGRATION_SYNC,
        entity_type="tally_job",
        entity_id=job.id,
        description=f"Tally job {job.operation.value} → {job.status.value}",
        status=job.status.value,
    )

    return {"ok": True, "job_id": job_id, "final_status": job.status.value}


# ─── Connector health (unauthenticated, for diagnostics) ────────────────────

@router.get("/connector/health")
def connector_health():
    return {"status": "ok", "service": "FinPilot Tally Integration"}
