"""
Unit tests for the delete-voucher flow.

Pure pytest — no live server, no database, no HTTP calls.
Everything is mocked with unittest.mock.

Run: python -m pytest backend/tests/unit/test_delete_flow.py --noconftest -v
"""
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.api.v1.endpoints.management import (
    _extract_tally_vnum_from_notes,
    _queue_tally_delete_voucher,
)
from app.models.tally_job import TallyJobOperation
from fastapi import HTTPException


# ─── Mock helpers ─────────────────────────────────────────────────────────────

def _invoice(
    tally_sync_status="local_only",
    tally_voucher_ref=None,
    invoice_number="INV-001",
    notes=None,
    paid_amount=0,
    invoice_type_value="SALES",
):
    rec = MagicMock()
    rec.id = uuid.uuid4()
    rec.tally_sync_status = tally_sync_status
    rec.tally_voucher_ref = tally_voucher_ref
    rec.invoice_number = invoice_number
    rec.notes = notes
    rec.paid_amount = paid_amount
    rec.invoice_type.value = invoice_type_value
    rec.invoice_date = None
    rec.is_deleted = False
    return rec


def _expense(
    tally_sync_status="local_only",
    tally_voucher_ref=None,
    title="Test Expense",
    notes=None,
    category="Purchase",
):
    rec = MagicMock()
    rec.id = uuid.uuid4()
    rec.tally_sync_status = tally_sync_status
    rec.tally_voucher_ref = tally_voucher_ref
    rec.title = title
    rec.notes = notes
    rec.category = category
    rec.expense_date = None
    rec.is_deleted = False
    return rec


def _make_db(record, connector="active"):
    """
    Build a MagicMock DB session.
    - First db.query(...).filter(...).first() → record
    - Second db.query(...).filter(...).first() → connector mock or None
    connector="active"  → returns a mock connector
    connector="none"    → returns None (no connector)
    connector="skip"    → only record query wired (for tests that don't reach connector lookup)
    """
    from app.models.tally_connector import TallyConnector

    if connector == "active":
        conn_obj = MagicMock(spec=TallyConnector)
        conn_obj.id = uuid.uuid4()
    else:
        conn_obj = None

    db = MagicMock()
    call_count = [0]

    def query_side_effect(model):
        call_count[0] += 1
        q = MagicMock()
        if call_count[0] == 1:
            q.filter.return_value.first.return_value = record
        else:
            q.filter.return_value.first.return_value = conn_obj
        # Also support .filter().all() for pending job cancellation
        q.filter.return_value.all.return_value = []
        return q

    if connector == "skip":
        # Simple: every query returns the record
        db.query.return_value.filter.return_value.first.return_value = record
        db.query.return_value.filter.return_value.all.return_value = []
    else:
        db.query.side_effect = query_side_effect

    return db


def _call_delete_invoice(rec, connector="skip"):
    from app.api.v1.endpoints.management import delete_voucher
    db = _make_db(rec, connector=connector)
    mock_user = MagicMock()
    mock_user.company_id = uuid.uuid4()
    mock_user.id = uuid.uuid4()
    with patch("app.api.v1.endpoints.management.audit_service"), \
         patch("app.api.v1.endpoints.management.TallyIntegrationJob"):
        return delete_voucher(
            entity_type="invoice",
            entity_id=str(rec.id),
            current_user=mock_user,
            db=db,
        )


def _call_delete_expense(rec, connector="skip"):
    from app.api.v1.endpoints.management import delete_voucher
    db = _make_db(rec, connector=connector)
    mock_user = MagicMock()
    mock_user.company_id = uuid.uuid4()
    mock_user.id = uuid.uuid4()
    with patch("app.api.v1.endpoints.management.audit_service"), \
         patch("app.api.v1.endpoints.management.TallyIntegrationJob"):
        return delete_voucher(
            entity_type="expense",
            entity_id=str(rec.id),
            current_user=mock_user,
            db=db,
        )


# ─── _extract_tally_vnum_from_notes ──────────────────────────────────────────

class TestExtractTallyVnum:
    def test_extracts_voucher_number_from_notes(self):
        assert _extract_tally_vnum_from_notes("[tally-sync] sales::TALLY-0004") == "TALLY-0004"

    def test_extracts_purchase_voucher_number(self):
        assert _extract_tally_vnum_from_notes("[tally-sync] purchase::PUR/2024-25/001") == "PUR/2024-25/001"

    def test_returns_empty_for_fallback_dedup_key(self):
        # Fallback key has extra "::" separators — not a real voucher number
        assert _extract_tally_vnum_from_notes("[tally-sync] sales::20240101::ABC::50000") == ""

    def test_returns_empty_when_no_tally_sync_tag(self):
        assert _extract_tally_vnum_from_notes("Some random notes") == ""

    def test_returns_empty_for_none(self):
        assert _extract_tally_vnum_from_notes(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert _extract_tally_vnum_from_notes("") == ""

    def test_extracts_receipt_type(self):
        assert _extract_tally_vnum_from_notes("[tally-sync] receipt::REC-001") == "REC-001"


# ─── _queue_tally_delete_voucher ─────────────────────────────────────────────

class TestQueueTallyDeleteVoucher:
    def _active_db(self):
        from app.models.tally_connector import TallyConnector
        db = MagicMock()
        connector = MagicMock(spec=TallyConnector)
        connector.id = uuid.uuid4()
        db.query.return_value.filter.return_value.first.return_value = connector
        return db

    def test_returns_true_and_adds_job_when_connector_active(self):
        db = self._active_db()
        result = _queue_tally_delete_voucher(
            db, uuid.uuid4(),
            voucher_ref="FP-abc123",
            voucher_type="Sales",
            entity_type="invoice",
            voucher_date="20260901",
            entity_id=str(uuid.uuid4()),
        )
        assert result is True
        db.add.assert_called_once()
        job = db.add.call_args[0][0]
        assert job.operation == TallyJobOperation.DELETE_VOUCHER
        assert job.payload["voucher_ref"] == "FP-abc123"
        assert job.payload["entity_type"] == "invoice"

    def test_returns_false_when_no_connector(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = _queue_tally_delete_voucher(
            db, uuid.uuid4(),
            voucher_ref="FP-001", voucher_type="Sales", entity_type="invoice",
        )
        assert result is False
        db.add.assert_not_called()

    def test_payload_includes_entity_id(self):
        db = self._active_db()
        eid = str(uuid.uuid4())
        _queue_tally_delete_voucher(
            db, uuid.uuid4(),
            voucher_ref="FP-002", voucher_type="Purchase",
            entity_type="expense", entity_id=eid,
        )
        assert db.add.call_args[0][0].payload["entity_id"] == eid

    def test_payload_includes_voucher_number_for_tally_native(self):
        db = self._active_db()
        _queue_tally_delete_voucher(
            db, uuid.uuid4(),
            voucher_ref="", voucher_number="TALLY-0004",
            voucher_type="Sales", entity_type="invoice",
        )
        payload = db.add.call_args[0][0].payload
        assert payload["voucher_number"] == "TALLY-0004"
        assert payload["voucher_ref"] == ""

    def test_idempotency_key_uses_delete_voucher_prefix(self):
        db = self._active_db()
        _queue_tally_delete_voucher(
            db, uuid.uuid4(),
            voucher_ref="FP-xyz", voucher_type="Sales", entity_type="invoice",
        )
        assert db.add.call_args[0][0].idempotency_key.startswith("delete_voucher::")


# ─── Invoice delete — 3 cases ────────────────────────────────────────────────

class TestInvoiceDeleteCases:

    # Case 3: local_only → immediate soft-delete
    def test_local_only_deleted_immediately(self):
        rec = _invoice(tally_sync_status="local_only")
        result = _call_delete_invoice(rec, connector="skip")
        assert result["status"] == "deleted"
        assert result["tally_confirmed"] is False
        assert rec.is_deleted is True

    # Case 2: pending → cancel in-flight job + immediate soft-delete
    def test_pending_deleted_immediately(self):
        rec = _invoice(tally_sync_status="pending", tally_voucher_ref=None)
        result = _call_delete_invoice(rec, connector="skip")
        assert result["status"] == "deleted"
        assert result["tally_confirmed"] is False
        assert rec.is_deleted is True

    # Case 1a: synced, FinPilot-created (REMOTEID present), connector active → queue job
    def test_synced_finpilot_created_queues_delete(self):
        rec = _invoice(
            tally_sync_status="synced",
            tally_voucher_ref="FP-abc123",
            notes="Created from FinPilot",   # no [tally-sync] tag
        )
        from app.api.v1.endpoints.management import delete_voucher
        db = _make_db(rec, connector="active")
        mock_user = MagicMock()
        mock_user.company_id = uuid.uuid4()
        mock_user.id = uuid.uuid4()
        with patch("app.api.v1.endpoints.management.audit_service"), \
             patch("app.api.v1.endpoints.management.TallyIntegrationJob") as mock_job:
            result = delete_voucher(
                entity_type="invoice", entity_id=str(rec.id),
                current_user=mock_user, db=db,
            )
        assert result["status"] == "pending"
        assert result["tally_confirmed"] is False
        assert "TallyPrime" in result["message"]
        assert rec.is_deleted is False
        assert rec.tally_sync_status == "delete_pending"
        # Job must have been queued
        mock_job.assert_called_once()
        payload = mock_job.call_args[1]["payload"]
        assert payload["voucher_ref"] == "FP-abc123"

    # Case 1b: synced, no connector → HTTP 409 (record stays visible)
    def test_synced_raises_409_when_no_connector(self):
        rec = _invoice(tally_sync_status="synced", tally_voucher_ref="FP-abc123", notes=None)
        from app.api.v1.endpoints.management import delete_voucher
        db = _make_db(rec, connector="none")
        mock_user = MagicMock()
        mock_user.company_id = uuid.uuid4()
        mock_user.id = uuid.uuid4()
        with patch("app.api.v1.endpoints.management.audit_service"), \
             patch("app.api.v1.endpoints.management.TallyIntegrationJob"):
            with pytest.raises(HTTPException) as exc_info:
                delete_voucher(
                    entity_type="invoice", entity_id=str(rec.id),
                    current_user=mock_user, db=db,
                )
        assert exc_info.value.status_code == 409
        assert rec.is_deleted is False   # record must be protected

    # Case 1c: synced Tally-native, voucher number in notes (pre-fix sync)
    def test_synced_tally_native_extracts_vnum_from_notes(self):
        rec = _invoice(
            tally_sync_status="synced",
            tally_voucher_ref=None,
            notes="[tally-sync] sales::TALLY-0004",
            invoice_number="TALLY-0001",
        )
        from app.api.v1.endpoints.management import delete_voucher
        db = _make_db(rec, connector="active")
        mock_user = MagicMock()
        mock_user.company_id = uuid.uuid4()
        mock_user.id = uuid.uuid4()
        with patch("app.api.v1.endpoints.management.audit_service"), \
             patch("app.api.v1.endpoints.management.TallyIntegrationJob") as mock_job:
            result = delete_voucher(
                entity_type="invoice", entity_id=str(rec.id),
                current_user=mock_user, db=db,
            )
        assert result["status"] == "pending"
        assert rec.tally_sync_status == "delete_pending"
        payload = mock_job.call_args[1]["payload"]
        # Must use the extracted voucher number (TALLY-0004), NOT the FinPilot number (TALLY-0001)
        assert payload["voucher_number"] == "TALLY-0004"
        assert payload["voucher_ref"] == ""

    # Case 1d: synced, no identifier at all → HTTP 400
    def test_synced_no_identifier_raises_400(self):
        rec = _invoice(
            tally_sync_status="synced",
            tally_voucher_ref=None,
            notes="[tally-sync] sales::20240101::SomeParty::50000",  # fallback key, no real vnum
        )
        with pytest.raises(HTTPException) as exc_info:
            _call_delete_invoice(rec, connector="skip")
        assert exc_info.value.status_code == 400

    # Paid invoice → HTTP 400
    def test_paid_invoice_raises_400(self):
        rec = _invoice(tally_sync_status="local_only", paid_amount=5000)
        with pytest.raises(HTTPException) as exc_info:
            _call_delete_invoice(rec, connector="skip")
        assert exc_info.value.status_code == 400
        assert "payment" in exc_info.value.detail.lower()

    # Not found → HTTP 404
    def test_not_found_raises_404(self):
        from app.api.v1.endpoints.management import delete_voucher
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        mock_user = MagicMock()
        mock_user.company_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            delete_voucher(
                entity_type="invoice", entity_id=str(uuid.uuid4()),
                current_user=mock_user, db=db,
            )
        assert exc_info.value.status_code == 404

    # delete_failed treated same as synced
    def test_delete_failed_re_queues_for_tally(self):
        rec = _invoice(tally_sync_status="delete_failed", tally_voucher_ref="FP-retry", notes=None)
        from app.api.v1.endpoints.management import delete_voucher
        db = _make_db(rec, connector="active")
        mock_user = MagicMock()
        mock_user.company_id = uuid.uuid4()
        mock_user.id = uuid.uuid4()
        with patch("app.api.v1.endpoints.management.audit_service"), \
             patch("app.api.v1.endpoints.management.TallyIntegrationJob"):
            result = delete_voucher(
                entity_type="invoice", entity_id=str(rec.id),
                current_user=mock_user, db=db,
            )
        assert result["status"] == "pending"
        assert rec.tally_sync_status == "delete_pending"


# ─── Expense delete — 3 cases ────────────────────────────────────────────────

class TestExpenseDeleteCases:

    def test_local_only_deleted_immediately(self):
        rec = _expense(tally_sync_status="local_only")
        result = _call_delete_expense(rec, connector="skip")
        assert result["status"] == "deleted"
        assert result["tally_confirmed"] is False
        assert rec.is_deleted is True

    def test_pending_deleted_immediately(self):
        rec = _expense(tally_sync_status="pending", tally_voucher_ref=None)
        result = _call_delete_expense(rec, connector="skip")
        assert result["status"] == "deleted"
        assert result["tally_confirmed"] is False
        assert rec.is_deleted is True

    def test_synced_raises_409_when_no_connector(self):
        rec = _expense(tally_sync_status="synced", tally_voucher_ref="FP-exp-001", notes=None)
        from app.api.v1.endpoints.management import delete_voucher
        db = _make_db(rec, connector="none")
        mock_user = MagicMock()
        mock_user.company_id = uuid.uuid4()
        mock_user.id = uuid.uuid4()
        with patch("app.api.v1.endpoints.management.audit_service"), \
             patch("app.api.v1.endpoints.management.TallyIntegrationJob"):
            with pytest.raises(HTTPException) as exc_info:
                delete_voucher(
                    entity_type="expense", entity_id=str(rec.id),
                    current_user=mock_user, db=db,
                )
        assert exc_info.value.status_code == 409
        assert rec.is_deleted is False

    def test_synced_no_identifier_raises_400(self):
        rec = _expense(
            tally_sync_status="synced",
            tally_voucher_ref=None,
            notes="[tally-sync] purchase::20240101::Vendor::10000",  # fallback key
        )
        with pytest.raises(HTTPException) as exc_info:
            _call_delete_expense(rec, connector="skip")
        assert exc_info.value.status_code == 400

    def test_voucher_type_inferred_from_category(self):
        """Each expense category must map to the correct TallyPrime voucher type."""
        from app.api.v1.endpoints.management import delete_voucher
        for category, expected_vtype in [
            ("Purchase",    "Purchase"),
            ("Receipt",     "Receipt"),
            ("Payment",     "Payment"),
            ("Contra",      "Contra"),
            ("Journal",     "Journal"),
            ("Credit Note", "Credit Note"),
            ("Debit Note",  "Debit Note"),
        ]:
            rec = _expense(
                tally_sync_status="synced",
                tally_voucher_ref="FP-001",
                notes=None,
                category=category,
            )
            db = _make_db(rec, connector="active")
            mock_user = MagicMock()
            mock_user.company_id = uuid.uuid4()
            mock_user.id = uuid.uuid4()
            with patch("app.api.v1.endpoints.management.audit_service"), \
                 patch("app.api.v1.endpoints.management.TallyIntegrationJob") as mock_job:
                delete_voucher(
                    entity_type="expense", entity_id=str(rec.id),
                    current_user=mock_user, db=db,
                )
            payload = mock_job.call_args[1]["payload"]
            assert payload["voucher_type"] == expected_vtype, \
                f"category={category!r}: expected {expected_vtype!r}, got {payload['voucher_type']!r}"

    def test_not_found_raises_404(self):
        from app.api.v1.endpoints.management import delete_voucher
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        mock_user = MagicMock()
        mock_user.company_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            delete_voucher(
                entity_type="expense", entity_id=str(uuid.uuid4()),
                current_user=mock_user, db=db,
            )
        assert exc_info.value.status_code == 404


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestDeleteEdgeCases:
    def test_invalid_entity_type_raises_400(self):
        from app.api.v1.endpoints.management import delete_voucher
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.company_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            delete_voucher(
                entity_type="ledger", entity_id=str(uuid.uuid4()),
                current_user=mock_user, db=db,
            )
        assert exc_info.value.status_code == 400
