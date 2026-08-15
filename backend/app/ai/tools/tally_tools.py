"""
Tally-specific read tools for the TallyAgent.
These query the job queue and connector status — no arbitrary SQL.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.tally_connector import TallyConnector, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, JobStatus
from datetime import datetime, timezone
import uuid


class TallyTools:
    def __init__(self, db: Session):
        self.db = db

    def get_tally_status(self, company_id: str) -> dict:
        cid = uuid.UUID(company_id)
        connector = self.db.query(TallyConnector).filter(
            TallyConnector.company_id == cid,
            TallyConnector.status == ConnectorStatus.ACTIVE,
        ).order_by(TallyConnector.created_at.desc()).first()

        if not connector:
            return {"connected": False, "message": "No active TallyPrime connector found for this company."}

        heartbeat_age = None
        is_online = False
        if connector.last_heartbeat:
            age_secs = (datetime.now(timezone.utc) - connector.last_heartbeat).total_seconds()
            heartbeat_age = int(age_secs)
            is_online = age_secs < 90

        return {
            "connected": True,
            "online": is_online,
            "connector_name": connector.connector_name,
            "device": connector.device_name,
            "tally_company": connector.tally_company_name,
            "last_heartbeat_seconds_ago": heartbeat_age,
            "status_message": "Online and receiving heartbeats" if is_online else "Connector registered but not responding",
        }

    def get_sync_jobs(self, company_id: str, status_filter: str = None, limit: int = 20) -> dict:
        cid = uuid.UUID(company_id)
        q = self.db.query(TallyIntegrationJob).filter(
            TallyIntegrationJob.company_id == cid
        )
        if status_filter:
            try:
                q = q.filter(TallyIntegrationJob.status == JobStatus(status_filter.upper()))
            except ValueError:
                pass
        jobs = q.order_by(TallyIntegrationJob.created_at.desc()).limit(limit).all()
        return {
            "jobs": [
                {
                    "id": str(j.id),
                    "operation": j.operation.value,
                    "status": j.status.value,
                    "retry_count": j.retry_count,
                    "error": j.error_message,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                }
                for j in jobs
            ],
            "count": len(jobs),
        }

    def get_failed_syncs(self, company_id: str) -> dict:
        cid = uuid.UUID(company_id)
        failed = self.db.query(TallyIntegrationJob).filter(
            TallyIntegrationJob.company_id == cid,
            TallyIntegrationJob.status == JobStatus.FAILED,
        ).order_by(TallyIntegrationJob.created_at.desc()).limit(50).all()

        pending = self.db.query(func.count(TallyIntegrationJob.id)).filter(
            TallyIntegrationJob.company_id == cid,
            TallyIntegrationJob.status.in_([JobStatus.PENDING, JobStatus.CLAIMED, JobStatus.RUNNING]),
        ).scalar() or 0

        return {
            "failed_count": len(failed),
            "pending_count": pending,
            "failed_jobs": [
                {
                    "operation": j.operation.value,
                    "error": j.error_message,
                    "retry_count": j.retry_count,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in failed
            ],
        }

    def get_tool_definitions(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_tally_status",
                    "description": "Get TallyPrime connector connection status, heartbeat, and online state",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_sync_jobs",
                    "description": "Get recent TallyPrime sync jobs with their status",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status_filter": {
                                "type": "string",
                                "description": "Filter by status: PENDING, SUCCESS, FAILED, RUNNING, RETRYING",
                            },
                            "limit": {"type": "integer", "description": "Max results, default 20"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_failed_syncs",
                    "description": "Get all failed TallyPrime sync operations and pending job counts",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def call_tool(self, tool_name: str, args: dict, company_id: str) -> dict:
        args["company_id"] = company_id
        tool_map = {
            "get_tally_status": self.get_tally_status,
            "get_sync_jobs": self.get_sync_jobs,
            "get_failed_syncs": self.get_failed_syncs,
        }
        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}"}
        import inspect
        fn = tool_map[tool_name]
        sig = inspect.signature(fn)
        filtered_args = {k: v for k, v in args.items() if k in sig.parameters}
        return fn(**filtered_args)
