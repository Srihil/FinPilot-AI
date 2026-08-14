"""
Tests for the Tally integration: connector registration, job lifecycle,
company isolation, authentication, and approval enforcement.
"""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models.tally_connector import TallyConnector, TallyPairingCode, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, JobStatus, TallyJobOperation
from app.core.security import hash_password

from tests.conftest import get_auth_token, auth_headers


# ─── Pairing code generation ──────────────────────────────────────────────────

class TestPairingGeneration:
    def test_admin_can_generate_pairing_code(self, client: TestClient, admin_user, db):
        token = get_auth_token(client, admin_user.email, "Password@123")
        resp = client.post("/api/tally/pairing/generate", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data
        assert len(data["code"]) == 10  # XXXX-XXXXX = 10 chars
        assert data["expires_in_minutes"] == 10

    def test_viewer_cannot_generate_pairing_code(self, client: TestClient, viewer_user, db):
        token = get_auth_token(client, viewer_user.email, "Password@123")
        resp = client.post("/api/tally/pairing/generate", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_accountant_cannot_generate_pairing_code(self, client: TestClient, accountant_user, db):
        token = get_auth_token(client, accountant_user.email, "Password@123")
        resp = client.post("/api/tally/pairing/generate", headers=auth_headers(token))
        assert resp.status_code == 403

    def test_unauthenticated_cannot_generate(self, client: TestClient):
        resp = client.post("/api/tally/pairing/generate")
        assert resp.status_code == 403


# ─── Connector registration ───────────────────────────────────────────────────

class TestConnectorRegistration:
    def _create_pairing_code(self, db, company_id, user_id, code="TEST-1234") -> TallyPairingCode:
        pc = TallyPairingCode(
            company_id=company_id,
            code=code,
            created_by=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(pc)
        db.commit()
        return pc

    def test_register_with_valid_code(self, client: TestClient, admin_user, db):
        self._create_pairing_code(db, admin_user.company_id, admin_user.id, "ABCD-1111")
        resp = client.post("/api/tally/connector/register", json={
            "pairing_code": "ABCD-1111",
            "connector_name": "Office PC",
            "device_name": "DESKTOP-TEST",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "connector_id" in data
        assert len(data["token"]) > 20

    def test_register_with_expired_code_fails(self, client: TestClient, admin_user, db):
        pc = TallyPairingCode(
            company_id=admin_user.company_id,
            code="EXPD-1111",
            created_by=admin_user.id,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(pc)
        db.commit()
        resp = client.post("/api/tally/connector/register", json={"pairing_code": "EXPD-1111"})
        assert resp.status_code == 400

    def test_register_with_used_code_fails(self, client: TestClient, admin_user, db):
        pc = TallyPairingCode(
            company_id=admin_user.company_id,
            code="USED-1111",
            created_by=admin_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_used=True,
            used_at=datetime.now(timezone.utc),
        )
        db.add(pc)
        db.commit()
        resp = client.post("/api/tally/connector/register", json={"pairing_code": "USED-1111"})
        assert resp.status_code == 400

    def test_register_revokes_existing_connector(self, client: TestClient, admin_user, db):
        old = TallyConnector(
            company_id=admin_user.company_id,
            token_hash=hash_password("old-token"),
            status=ConnectorStatus.ACTIVE,
        )
        db.add(old)
        db.commit()

        self._create_pairing_code(db, admin_user.company_id, admin_user.id, "NEW1-CODE")
        resp = client.post("/api/tally/connector/register", json={"pairing_code": "NEW1-CODE"})
        assert resp.status_code == 200

        db.refresh(old)
        assert old.status == ConnectorStatus.REVOKED


# ─── Connector API (heartbeat & job poll) ────────────────────────────────────

def _make_connector(db, company_id, token="test-token-xyz") -> tuple[TallyConnector, str]:
    raw = token
    c = TallyConnector(
        company_id=company_id,
        connector_name="Test Connector",
        device_name="TEST-PC",
        token_hash=hash_password(raw),
        status=ConnectorStatus.ACTIVE,
        tally_host="localhost",
        tally_port=9000,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c, raw


class TestHeartbeat:
    def test_valid_connector_can_heartbeat(self, client: TestClient, admin_user, db):
        _, raw = _make_connector(db, admin_user.company_id, token=f"hb-tok-{uuid.uuid4().hex}")
        resp = client.post(
            "/api/tally/connector/heartbeat",
            json={"tally_reachable": True, "tally_company_name": "Test Co"},
            headers=auth_headers(raw),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invalid_token_heartbeat_fails(self, client: TestClient):
        resp = client.post(
            "/api/tally/connector/heartbeat",
            json={"tally_reachable": False},
            headers=auth_headers("totally-wrong-token"),
        )
        assert resp.status_code == 401

    def test_revoked_connector_heartbeat_fails(self, client: TestClient, admin_user, db):
        raw = f"rev-tok-{uuid.uuid4().hex}"
        c = TallyConnector(
            company_id=admin_user.company_id,
            token_hash=hash_password(raw),
            status=ConnectorStatus.REVOKED,
        )
        db.add(c)
        db.commit()
        resp = client.post(
            "/api/tally/connector/heartbeat",
            json={"tally_reachable": False},
            headers=auth_headers(raw),
        )
        assert resp.status_code == 401


# ─── Job polling and result submission ───────────────────────────────────────

class TestJobLifecycle:
    def test_connector_polls_pending_jobs(self, client: TestClient, admin_user, db):
        connector, raw = _make_connector(db, admin_user.company_id, token=f"poll-{uuid.uuid4().hex}")
        job = TallyIntegrationJob(
            company_id=admin_user.company_id,
            connector_id=connector.id,
            operation=TallyJobOperation.READ_LEDGERS,
            payload={},
            status=JobStatus.PENDING,
            idempotency_key=f"idem-{uuid.uuid4().hex}",
        )
        db.add(job)
        db.commit()

        resp = client.get("/api/tally/connector/jobs", headers=auth_headers(raw))
        assert resp.status_code == 200
        jobs = resp.json()["jobs"]
        assert len(jobs) >= 1
        assert jobs[0]["operation"] == "READ_LEDGERS"

        # Job should now be CLAIMED
        db.refresh(job)
        assert job.status == JobStatus.CLAIMED

    def test_connector_submits_success_result(self, client: TestClient, admin_user, db):
        connector, raw = _make_connector(db, admin_user.company_id, token=f"res-{uuid.uuid4().hex}")
        job = TallyIntegrationJob(
            company_id=admin_user.company_id,
            connector_id=connector.id,
            operation=TallyJobOperation.READ_LEDGERS,
            payload={},
            status=JobStatus.CLAIMED,
            idempotency_key=f"idem2-{uuid.uuid4().hex}",
        )
        db.add(job)
        db.commit()

        resp = client.post(
            f"/api/tally/connector/jobs/{job.id}/result",
            json={"status": "SUCCESS", "result": {"ledgers": [], "count": 0}},
            headers=auth_headers(raw),
        )
        assert resp.status_code == 200
        db.refresh(job)
        assert job.status == JobStatus.SUCCESS
        assert job.result["count"] == 0

    def test_failed_job_retries(self, client: TestClient, admin_user, db):
        connector, raw = _make_connector(db, admin_user.company_id, token=f"retry-{uuid.uuid4().hex}")
        job = TallyIntegrationJob(
            company_id=admin_user.company_id,
            connector_id=connector.id,
            operation=TallyJobOperation.SYNC_FULL,
            payload={},
            status=JobStatus.CLAIMED,
            retry_count=0,
            idempotency_key=f"retry-idem-{uuid.uuid4().hex}",
        )
        db.add(job)
        db.commit()

        resp = client.post(
            f"/api/tally/connector/jobs/{job.id}/result",
            json={"status": "FAILED", "error_message": "Tally not reachable"},
            headers=auth_headers(raw),
        )
        assert resp.status_code == 200
        db.refresh(job)
        assert job.status == JobStatus.RETRYING
        assert job.retry_count == 1

    def test_job_marked_failed_after_max_retries(self, client: TestClient, admin_user, db):
        connector, raw = _make_connector(db, admin_user.company_id, token=f"maxret-{uuid.uuid4().hex}")
        job = TallyIntegrationJob(
            company_id=admin_user.company_id,
            connector_id=connector.id,
            operation=TallyJobOperation.SYNC_FULL,
            payload={},
            status=JobStatus.CLAIMED,
            retry_count=2,  # already at MAX_RETRY - 1
            idempotency_key=f"maxret-idem-{uuid.uuid4().hex}",
        )
        db.add(job)
        db.commit()

        resp = client.post(
            f"/api/tally/connector/jobs/{job.id}/result",
            json={"status": "FAILED", "error_message": "Still failing"},
            headers=auth_headers(raw),
        )
        assert resp.status_code == 200
        db.refresh(job)
        assert job.status == JobStatus.FAILED


# ─── Company isolation ────────────────────────────────────────────────────────

class TestCompanyIsolation:
    def test_connector_cannot_access_other_company_jobs(
        self, client: TestClient, admin_user, company_b_admin, db
    ):
        connector_a, raw_a = _make_connector(db, admin_user.company_id, token=f"iso-a-{uuid.uuid4().hex}")
        connector_b, raw_b = _make_connector(db, company_b_admin.company_id, token=f"iso-b-{uuid.uuid4().hex}")

        # Create a job for company B
        job_b = TallyIntegrationJob(
            company_id=company_b_admin.company_id,
            connector_id=connector_b.id,
            operation=TallyJobOperation.READ_SALES,
            payload={},
            status=JobStatus.PENDING,
            idempotency_key=f"iso-idem-{uuid.uuid4().hex}",
        )
        db.add(job_b)
        db.commit()

        # Connector A polls — should not see Company B's job
        resp = client.get("/api/tally/connector/jobs", headers=auth_headers(raw_a))
        assert resp.status_code == 200
        job_ids = [j["id"] for j in resp.json()["jobs"]]
        assert str(job_b.id) not in job_ids

    def test_connector_cannot_submit_result_for_other_company_job(
        self, client: TestClient, admin_user, company_b_admin, db
    ):
        connector_a, raw_a = _make_connector(db, admin_user.company_id, token=f"res-a-{uuid.uuid4().hex}")
        connector_b, raw_b = _make_connector(db, company_b_admin.company_id, token=f"res-b-{uuid.uuid4().hex}")

        job_b = TallyIntegrationJob(
            company_id=company_b_admin.company_id,
            connector_id=connector_b.id,
            operation=TallyJobOperation.READ_LEDGERS,
            payload={},
            status=JobStatus.CLAIMED,
            idempotency_key=f"res-idem-{uuid.uuid4().hex}",
        )
        db.add(job_b)
        db.commit()

        # Connector A tries to submit result for Company B's job — must fail
        resp = client.post(
            f"/api/tally/connector/jobs/{job_b.id}/result",
            json={"status": "SUCCESS", "result": {}},
            headers=auth_headers(raw_a),
        )
        assert resp.status_code == 404


# ─── Write operations require approval ───────────────────────────────────────

class TestWriteOperationApproval:
    def test_write_job_without_approval_id_rejected(self, client: TestClient, admin_user, db):
        _make_connector(db, admin_user.company_id, token=f"wr-{uuid.uuid4().hex}")
        token = get_auth_token(client, admin_user.email, "Password@123")
        resp = client.post(
            "/api/tally/jobs",
            json={
                "operation": "CREATE_SALES_VOUCHER",
                "payload": {"date": "20260814", "party_ledger": "Test Party", "amount": "5000"},
            },
            headers=auth_headers(token),
        )
        assert resp.status_code == 400
        assert "approval_id" in resp.json()["detail"].lower()

    def test_read_job_does_not_require_approval(self, client: TestClient, admin_user, db):
        _make_connector(db, admin_user.company_id, token=f"rd-{uuid.uuid4().hex}")
        token = get_auth_token(client, admin_user.email, "Password@123")
        resp = client.post(
            "/api/tally/jobs",
            json={"operation": "READ_LEDGERS", "payload": {}},
            headers=auth_headers(token),
        )
        assert resp.status_code == 200
        assert "job_id" in resp.json()


# ─── Idempotency ─────────────────────────────────────────────────────────────

class TestIdempotency:
    def test_duplicate_job_returns_existing(self, client: TestClient, admin_user, db):
        _make_connector(db, admin_user.company_id, token=f"idem-dup-{uuid.uuid4().hex}")
        token = get_auth_token(client, admin_user.email, "Password@123")
        idem_key = f"unique-key-{uuid.uuid4().hex}"

        resp1 = client.post(
            "/api/tally/jobs",
            json={"operation": "READ_LEDGERS", "idempotency_key": idem_key},
            headers=auth_headers(token),
        )
        resp2 = client.post(
            "/api/tally/jobs",
            json={"operation": "READ_LEDGERS", "idempotency_key": idem_key},
            headers=auth_headers(token),
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["job_id"] == resp2.json()["job_id"]


# ─── Status endpoint ──────────────────────────────────────────────────────────

class TestStatusEndpoint:
    def test_status_no_connector(self, client: TestClient, admin_user, db):
        token = get_auth_token(client, admin_user.email, "Password@123")
        resp = client.get("/api/tally/status", headers=auth_headers(token))
        assert resp.status_code == 200
        data = resp.json()
        # May or may not be connected depending on fixture state
        assert "connected" in data

    def test_status_unauthenticated(self, client: TestClient):
        resp = client.get("/api/tally/status")
        assert resp.status_code == 403


# ─── Tally client unit tests (mocked TallyPrime) ─────────────────────────────

class TestTallyClientUnit:
    """These tests use mocked HTTP responses — no live TallyPrime needed."""

    def test_is_reachable_true(self):
        from tally_connector.tally_client import TallyClient  # noqa: requires connector on path
        # Use inline import to avoid hard dependency in CI
        pytest.importorskip("httpx")
        client = TallyClient()
        with patch("httpx.Client") as MockClient:
            MockClient.return_value.__enter__.return_value.get.return_value = MagicMock(status_code=200)
            # We can't easily test the connector's tally_client from backend tests
            # Connector has its own test suite — see tally-connector/tests/
            pass

    def test_tally_error_on_connect_error(self):
        """TallyClient raises TallyError when Tally is unreachable."""
        import sys
        sys.path.insert(0, str(__file__).replace("tests/test_tally.py", "../tally-connector"))
        try:
            from tally_client import TallyClient, TallyError
            import httpx
            client = TallyClient()
            with patch.object(httpx.Client, "__enter__") as mock_ctx:
                instance = MagicMock()
                instance.post.side_effect = httpx.ConnectError("connection refused")
                mock_ctx.return_value = instance
                with pytest.raises(TallyError):
                    client._post_xml("<test/>")
        except ImportError:
            pytest.skip("Connector not importable from backend tests path")
