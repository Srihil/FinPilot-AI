"""
Unit tests for connector job execution logic.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from connector import execute_job, ALLOWED_OPERATIONS
from tally_client import TallyClient, TallyError


def _mk_job(op: str, payload: dict = None) -> dict:
    return {"id": "test-job-id", "operation": op, "payload": payload or {}, "idempotency_key": "k1"}


class TestExecuteJob:
    def test_read_ledgers_success(self):
        tally = MagicMock(spec=TallyClient)
        tally.get_ledgers.return_value = [{"name": "Cash", "group": "Cash-in-Hand", "closing_balance": "5000"}]
        result, error = execute_job(tally, _mk_job("READ_LEDGERS"))
        assert error is None
        assert result["count"] == 1
        assert result["ledgers"][0]["name"] == "Cash"

    def test_read_sales_success(self):
        tally = MagicMock(spec=TallyClient)
        tally.get_sales.return_value = [{"date": "20260814", "voucher_type": "Sales", "amount": "5000", "party": "X", "narration": ""}]
        result, error = execute_job(tally, _mk_job("READ_SALES", {"from_date": "20260801", "to_date": "20260814"}))
        assert error is None
        assert result["count"] == 1

    def test_read_stock_items_success(self):
        tally = MagicMock(spec=TallyClient)
        tally.get_stock_items.return_value = [{"name": "Widget", "unit": "Nos", "closing_balance": "50", "closing_rate": "200"}]
        result, error = execute_job(tally, _mk_job("READ_STOCK_ITEMS"))
        assert error is None
        assert result["count"] == 1

    def test_create_sales_voucher_success(self):
        tally = MagicMock(spec=TallyClient)
        tally.create_sales_voucher.return_value = {"created": 1}
        payload = {"date": "20260814", "party_ledger": "Test", "amount": "1000"}
        result, error = execute_job(tally, _mk_job("CREATE_SALES_VOUCHER", payload))
        assert error is None
        assert result["created"] == 1

    def test_create_ledger_success(self):
        tally = MagicMock(spec=TallyClient)
        tally.create_ledger.return_value = {"created": 1}
        result, error = execute_job(tally, _mk_job("CREATE_LEDGER", {"name": "New Party", "group": "Sundry Debtors"}))
        assert error is None
        assert result["created"] == 1

    def test_sync_full_returns_summary(self):
        tally = MagicMock(spec=TallyClient)
        tally.get_ledgers.return_value = [{"name": "Cash", "group": "x", "closing_balance": "0"}]
        tally.get_stock_items.return_value = []
        result, error = execute_job(tally, _mk_job("SYNC_FULL"))
        assert error is None
        assert result["synced"] is True
        assert result["ledger_count"] == 1

    def test_unknown_operation_returns_error(self):
        tally = MagicMock(spec=TallyClient)
        result, error = execute_job(tally, _mk_job("INJECT_ARBITRARY_XML"))
        assert result is None
        assert "not allowed" in error

    def test_tally_error_propagated_as_error(self):
        tally = MagicMock(spec=TallyClient)
        tally.get_ledgers.side_effect = TallyError("Tally offline")
        result, error = execute_job(tally, _mk_job("READ_LEDGERS"))
        assert result is None
        assert "Tally offline" in error

    def test_unexpected_exception_returns_error(self):
        tally = MagicMock(spec=TallyClient)
        tally.get_ledgers.side_effect = RuntimeError("unexpected crash")
        result, error = execute_job(tally, _mk_job("READ_LEDGERS"))
        assert result is None
        assert "Internal error" in error


class TestAllowedOperations:
    def test_all_expected_operations_allowed(self):
        expected = {
            # Read operations
            "READ_COMPANIES", "READ_LEDGERS", "READ_VOUCHERS", "READ_SALES",
            "READ_PURCHASES", "READ_RECEIVABLES", "READ_PAYABLES", "READ_STOCK_ITEMS",
            # Accounting master writes
            "CREATE_LEDGER", "CREATE_GROUP",
            # Inventory masters
            "CREATE_STOCK_ITEM", "CREATE_STOCK_GROUP", "CREATE_UNIT", "CREATE_GODOWN", "CREATE_STOCK_CATEGORY",
            # Voucher type
            "CREATE_VOUCHER_TYPE",
            # Voucher writes
            "CREATE_SALES_VOUCHER", "CREATE_PURCHASE_VOUCHER", "CREATE_RECEIPT_VOUCHER",
            "CREATE_PAYMENT_VOUCHER", "CREATE_JOURNAL_VOUCHER",
            "CREATE_CREDIT_NOTE", "CREATE_DEBIT_NOTE", "CREATE_CONTRA_VOUCHER",
            # Stock transaction vouchers
            "CREATE_STOCK_JOURNAL", "CREATE_PHYSICAL_STOCK",
            "CREATE_DELIVERY_NOTE", "CREATE_RECEIPT_NOTE",
            "CREATE_REJECTION_IN", "CREATE_REJECTION_OUT",
            # Delete operations (masters)
            "DELETE_LEDGER", "DELETE_STOCK_ITEM", "DELETE_STOCK_GROUP", "DELETE_UNIT", "DELETE_GODOWN",
            "DELETE_STOCK_CATEGORY", "DELETE_VOUCHER_TYPE",
            # Permanent voucher delete in TallyPrime (Tally-confirmed-first)
            "DELETE_VOUCHER",
            # Sync
            "SYNC_FULL", "SYNC_PARTIAL",
        }
        assert expected == ALLOWED_OPERATIONS

    def test_cancel_voucher_not_allowed(self):
        # CANCEL_VOUCHER (old name) was replaced by DELETE_VOUCHER
        assert "CANCEL_VOUCHER" not in ALLOWED_OPERATIONS

    def test_arbitrary_sql_not_allowed(self):
        assert "EXECUTE_SQL" not in ALLOWED_OPERATIONS
        assert "EXECUTE_XML" not in ALLOWED_OPERATIONS
        assert "SHELL" not in ALLOWED_OPERATIONS


class TestDeleteVoucher:
    def test_delete_voucher_by_remoteid(self):
        tally = MagicMock(spec=TallyClient)
        tally.delete_voucher.return_value = {"deleted": 1, "altered": 0, "voucher_ref": "FP-001", "voucher_number": ""}
        payload = {
            "voucher_ref": "FP-001",
            "voucher_type": "Sales",
            "date": "20260901",
        }
        result, error = execute_job(tally, _mk_job("DELETE_VOUCHER", payload))
        assert error is None
        assert result["deleted"] == 1
        tally.delete_voucher.assert_called_once_with(payload)

    def test_delete_voucher_by_voucher_number(self):
        tally = MagicMock(spec=TallyClient)
        tally.delete_voucher.return_value = {"deleted": 1, "altered": 0, "voucher_ref": "", "voucher_number": "TALLY-0004"}
        payload = {
            "voucher_ref": "",
            "voucher_number": "TALLY-0004",
            "voucher_type": "Sales",
            "date": "20260901",
        }
        result, error = execute_job(tally, _mk_job("DELETE_VOUCHER", payload))
        assert error is None
        assert result["deleted"] == 1

    def test_delete_voucher_tally_error_propagated(self):
        tally = MagicMock(spec=TallyClient)
        tally.delete_voucher.side_effect = TallyError("Voucher not found in TallyPrime")
        result, error = execute_job(tally, _mk_job("DELETE_VOUCHER", {"voucher_ref": "FP-999", "voucher_type": "Sales"}))
        assert result is None
        assert "Voucher not found" in error

    def test_cancel_voucher_operation_rejected(self):
        tally = MagicMock(spec=TallyClient)
        result, error = execute_job(tally, _mk_job("CANCEL_VOUCHER", {"voucher_ref": "FP-001"}))
        assert result is None
        assert "not allowed" in error
