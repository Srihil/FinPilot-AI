"""Queue a TallyPrime write job without requiring approval — used for auto-sync after entity creation."""
from sqlalchemy.orm import Session
from app.models.tally_connector import TallyConnector, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, TallyJobOperation, JobStatus
import uuid as uuid_mod
import logging

logger = logging.getLogger(__name__)


def queue_tally_write(
    db: Session,
    company_id,
    operation: str,
    payload: dict,
    idempotency_key: str = None,
) -> bool:
    """
    Find the active connector for the company and create a PENDING write job.
    Returns True if queued, False if no active connector (silently skip — user may not have Tally).
    Does NOT commit — caller controls transaction.
    """
    try:
        connector = db.query(TallyConnector).filter(
            TallyConnector.company_id == company_id,
            TallyConnector.status == ConnectorStatus.ACTIVE,
        ).first()
        if not connector:
            return False

        key = idempotency_key or f"{operation}:{uuid_mod.uuid4()}"
        job = TallyIntegrationJob(
            company_id=company_id,
            connector_id=connector.id,
            operation=TallyJobOperation(operation),
            payload=payload,
            status=JobStatus.PENDING,
            idempotency_key=key,
        )
        db.add(job)
        return True
    except Exception as e:
        logger.warning("Failed to queue Tally write job %s: %s", operation, e)
        return False
