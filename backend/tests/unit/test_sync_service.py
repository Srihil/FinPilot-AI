"""
Unit tests for tally_sync_service.py — no database, no server.

Tests every sync function and the main process_sync_result entry point.
Matches the exact data that comes from TallyPrime (as seen in the Day Book screenshot:
  - Cash Receipt ₹25,000
  - Kapoor Suppliers Purchase ₹18,500
  - Remote Stock Journal 5 Units)

Run: python -m pytest backend/tests/unit/test_sync_service.py --noconftest -v
"""
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.tally_sync_service import (
    sync_ledgers,
    sync_godowns,
    sync_stock_groups,
    sync_stock_categories,
    sync_units,
    sync_groups,
    sync_voucher_types,
    sync_stock_items,
    sync_vouchers,
    sync_stock_transactions,
    process_sync_result,
)


# ─── Mock DB helpers ─────────────────────────────────────────────────────────

def _db(existing=None):
    """DB that returns `existing` for every .first() call, None otherwise."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.update.return_value = 0
    return db


CID = uuid.uuid4()


# ─── sync_ledgers ─────────────────────────────────────────────────────────────

class TestSyncLedgers:
    def test_creates_ledger_for_new_entry(self):
        db = _db(existing=None)
        result = sync_ledgers(db, CID, [
            {"name": "HDFC Bank", "group": "Bank Accounts", "closing_balance": "50000"},
        ])
        assert result["ledgers"] == 1
        assert result["customers"] == 0
        assert result["vendors"] == 0
        db.add.assert_called()

    def test_maps_sundry_debtor_to_customer(self):
        db = _db(existing=None)
        # Two queries: TallyLedger lookup + Customer lookup
        db.query.return_value.filter.return_value.first.side_effect = [None, None]
        result = sync_ledgers(db, CID, [
            {"name": "Kumar Enterprises", "group": "Sundry Debtors", "closing_balance": "0"},
        ])
        assert result["customers"] == 1
        assert result["vendors"] == 0

    def test_maps_sundry_creditor_to_vendor(self):
        db = _db(existing=None)
        db.query.return_value.filter.return_value.first.side_effect = [None, None]
        result = sync_ledgers(db, CID, [
            {"name": "Kapoor Suppliers", "group": "Sundry Creditors", "closing_balance": "0"},
        ])
        assert result["vendors"] == 1
        assert result["customers"] == 0

    def test_updates_existing_ledger(self):
        existing = MagicMock()
        db = _db(existing=existing)
        result = sync_ledgers(db, CID, [
            {"name": "Cash", "group": "Cash-in-Hand", "closing_balance": "10000"},
        ])
        assert result["ledgers"] == 0   # updated, not created
        assert existing.tally_sync_status == "synced"
        assert float(existing.closing_balance) == 10000.0

    def test_skips_empty_name(self):
        db = _db(existing=None)
        result = sync_ledgers(db, CID, [{"name": "", "group": "Sales", "closing_balance": "0"}])
        assert result["ledgers"] == 0
        db.add.assert_not_called()


# ─── sync_godowns ────────────────────────────────────────────────────────────

class TestSyncGodowns:
    def test_creates_new_godown(self):
        db = _db(existing=None)
        result = sync_godowns(db, CID, [{"name": "Main Location", "parent": None}])
        assert result["created"] == 1
        assert result["updated"] == 0
        db.add.assert_called_once()

    def test_creates_godown_with_parent(self):
        db = _db(existing=None)
        result = sync_godowns(db, CID, [{"name": "Chennai", "parent": "Main Location"}])
        assert result["created"] == 1
        added = db.add.call_args[0][0]
        assert added.parent == "Main Location"

    def test_updates_existing_godown(self):
        existing = MagicMock()
        db = _db(existing=existing)
        result = sync_godowns(db, CID, [{"name": "Chennai", "parent": "HQ"}])
        assert result["updated"] == 1
        assert existing.parent == "HQ"
        assert existing.tally_sync_status == "synced"

    def test_skips_empty_name(self):
        db = _db(existing=None)
        result = sync_godowns(db, CID, [{"name": "", "parent": None}])
        assert result["created"] == 0


# ─── sync_stock_categories ───────────────────────────────────────────────────

class TestSyncStockCategories:
    def test_creates_new_category(self):
        db = _db(existing=None)
        result = sync_stock_categories(db, CID, [{"name": "Electronics", "parent": None}])
        assert result["created"] == 1
        db.add.assert_called_once()

    def test_skips_primary(self):
        db = _db(existing=None)
        result = sync_stock_categories(db, CID, [{"name": "Primary", "parent": None}])
        assert result["created"] == 0
        db.add.assert_not_called()

    def test_updates_existing_category(self):
        existing = MagicMock()
        db = _db(existing=existing)
        result = sync_stock_categories(db, CID, [{"name": "Electronics", "parent": "Tech"}])
        assert result["updated"] == 1
        assert existing.parent == "Tech"


# ─── sync_units ──────────────────────────────────────────────────────────────

class TestSyncUnits:
    def test_creates_unit(self):
        db = _db(existing=None)
        result = sync_units(db, CID, [
            {"name": "Nos", "symbol": "Nos", "decimal_places": 0, "unit_type": "simple"},
        ])
        assert result["created"] == 1
        db.add.assert_called_once()

    def test_updates_existing_unit(self):
        existing = MagicMock()
        db = _db(existing=existing)
        result = sync_units(db, CID, [{"name": "Kg", "symbol": "Kg", "decimal_places": 2}])
        assert result["updated"] == 1
        assert existing.symbol == "Kg"


# ─── sync_groups (account groups) ────────────────────────────────────────────

class TestSyncGroups:
    def test_creates_group(self):
        db = _db(existing=None)
        result = sync_groups(db, CID, [
            {"name": "Indirect Expenses", "parent": "Primary"},
        ])
        assert result["created"] == 1
        added = db.add.call_args[0][0]
        assert added.parent is None  # "Primary" is normalized to None

    def test_skips_primary(self):
        db = _db(existing=None)
        result = sync_groups(db, CID, [{"name": "Primary", "parent": None}])
        assert result["created"] == 0


# ─── sync_voucher_types ───────────────────────────────────────────────────────

class TestSyncVoucherTypes:
    def test_creates_voucher_type(self):
        db = _db(existing=None)
        result = sync_voucher_types(db, CID, [
            {"name": "GST Bill", "parent": "Sales", "numbering_method": "Automatic", "is_active": True},
        ])
        assert result["created"] == 1

    def test_updates_existing(self):
        existing = MagicMock()
        db = _db(existing=existing)
        result = sync_voucher_types(db, CID, [
            {"name": "GST Bill", "parent": "Sales", "numbering_method": "Manual", "is_active": True},
        ])
        assert result["updated"] == 1
        assert existing.numbering_method == "Manual"


# ─── sync_stock_items ─────────────────────────────────────────────────────────

class TestSyncStockItems:
    def test_creates_stock_item_with_group(self):
        """Matches TallyPrime screenshot: Remote is under Tablets (under Electronics)."""
        db = _db(existing=None)
        result = sync_stock_items(db, CID, [
            {"name": "Remote", "stock_group": "Tablets", "unit": "Nos",
             "closing_balance": "50 Nos", "closing_rate": "500"},
        ])
        assert result["created"] == 1
        added = db.add.call_args[0][0]
        assert added.stock_group == "Tablets"
        assert added.name == "Remote"

    def test_creates_stock_item_without_group(self):
        db = _db(existing=None)
        result = sync_stock_items(db, CID, [
            {"name": "FP-TEST-Stock-Item", "stock_group": None, "unit": "Nos",
             "closing_balance": "0", "closing_rate": "0"},
        ])
        assert result["created"] == 1
        added = db.add.call_args[0][0]
        assert added.stock_group is None

    def test_all_tally_screenshot_items_created(self):
        """Verify all 12 items from the TallyPrime screenshot are created correctly."""
        tally_items = [
            # ABC Traders group
            {"name": "Bed",             "stock_group": "ABC Traders", "unit": "Nos", "closing_balance": "0", "closing_rate": "0"},
            {"name": "Mattress",        "stock_group": "ABC Traders", "unit": "Nos", "closing_balance": "0", "closing_rate": "0"},
            {"name": "pencils",         "stock_group": "ABC Traders", "unit": "Nos", "closing_balance": "0", "closing_rate": "0"},
            {"name": "Pillow",          "stock_group": "ABC Traders", "unit": "Nos", "closing_balance": "0", "closing_rate": "0"},
            # Mobile Phones subgroup (under Electronics)
            {"name": "blankets",        "stock_group": "Mobile Phones", "unit": "Nos", "closing_balance": "0", "closing_rate": "0"},
            {"name": "Samsung Galaxy",  "stock_group": "Mobile Phones", "unit": "Nos", "closing_balance": "0", "closing_rate": "25000"},
            # Tablets subgroup (under Electronics)
            {"name": "IPhone",          "stock_group": "Tablets", "unit": "Nos", "closing_balance": "0", "closing_rate": "0"},
            {"name": "Phone",           "stock_group": "Tablets", "unit": "Nos", "closing_balance": "0", "closing_rate": "0"},
            {"name": "Remote",          "stock_group": "Tablets", "unit": "Nos", "closing_balance": "50 Nos", "closing_rate": "500"},
            # Furniture group
            {"name": "Office Chair",    "stock_group": "Furniture", "unit": "Nos", "closing_balance": "0", "closing_rate": "5000"},
            # Sahil stocks group
            {"name": "Laptop",          "stock_group": "Sahil stocks", "unit": "Nos", "closing_balance": "0", "closing_rate": "45000"},
            # No group
            {"name": "FP-TEST-Stock-Item", "stock_group": None, "unit": "Nos", "closing_balance": "0", "closing_rate": "0"},
        ]
        db = _db(existing=None)
        result = sync_stock_items(db, CID, tally_items)
        assert result["created"] == 12

        # Verify each call had the right stock_group
        calls = db.add.call_args_list
        assert len(calls) == 12
        created_groups = {c[0][0].name: c[0][0].stock_group for c in calls}
        assert created_groups["Remote"] == "Tablets"
        assert created_groups["Laptop"] == "Sahil stocks"
        assert created_groups["Office Chair"] == "Furniture"
        assert created_groups["FP-TEST-Stock-Item"] is None

    def test_updates_existing_stock_item_group(self):
        existing = MagicMock()
        db = _db(existing=existing)
        result = sync_stock_items(db, CID, [
            {"name": "Remote", "stock_group": "Tablets", "unit": "Nos",
             "closing_balance": "60 Nos", "closing_rate": "600"},
        ])
        assert result["updated"] == 1
        assert float(existing.rate) == 600.0
        assert existing.stock_group == "Tablets"


# ─── sync_stock_transactions ─────────────────────────────────────────────────

class TestSyncStockTransactions:
    # Sample data matching the TallyPrime Day Book screenshot:
    # "Remote" Stock Journal Vch #7 → 5 Units (Main Location → Chennai)
    STOCK_JOURNAL = {
        "transaction_type": "STOCK_JOURNAL",
        "transaction_number": "7",
        "date": "20260901",
        "narration": "Transfer Remote to Chennai",
        "party": "",
        "from_godown": "Main Location",
        "to_godown": "Chennai",
        "voucher_type_name": "Stock Journal",
        "entries": [
            {"stock_item_name": "Remote", "quantity": 5, "unit": "Nos", "rate": 0, "godown": "Main Location", "inward": False},
            {"stock_item_name": "Remote", "quantity": 5, "unit": "Nos", "rate": 0, "godown": "Chennai",       "inward": True},
        ],
    }

    def test_creates_stock_journal(self):
        db = _db(existing=None)
        result = sync_stock_transactions(db, CID, [self.STOCK_JOURNAL])
        assert result["created"] == 1
        assert result["updated"] == 0
        added = db.add.call_args[0][0]
        assert added.transaction_type == "STOCK_JOURNAL"
        assert added.transaction_number == "7"
        assert added.from_godown == "Main Location"
        assert added.to_godown == "Chennai"
        assert len(added.entries) == 2

    def test_creates_physical_stock(self):
        db = _db(existing=None)
        txn = {
            "transaction_type": "PHYSICAL_STOCK",
            "transaction_number": "PS-1",
            "date": "20260901",
            "narration": "Physical count",
            "party": "",
            "from_godown": "",
            "to_godown": "Main Location",
            "voucher_type_name": "Physical Stock",
            "entries": [
                {"stock_item_name": "Remote", "quantity": 50, "unit": "Nos", "rate": 0, "godown": "Main Location", "inward": True},
            ],
        }
        result = sync_stock_transactions(db, CID, [txn])
        assert result["created"] == 1
        added = db.add.call_args[0][0]
        assert added.transaction_type == "PHYSICAL_STOCK"

    def test_creates_delivery_note(self):
        db = _db(existing=None)
        txn = {
            "transaction_type": "DELIVERY_NOTE",
            "transaction_number": "DN-5",
            "date": "20260901",
            "narration": "Deliver to Kumar Enterprises",
            "party": "Kumar Enterprises",
            "from_godown": "Main Location",
            "to_godown": "",
            "voucher_type_name": "Delivery Note",
            "entries": [
                {"stock_item_name": "Laptop", "quantity": 2, "unit": "Nos", "rate": 45000, "godown": "Main Location", "inward": False},
            ],
        }
        result = sync_stock_transactions(db, CID, [txn])
        assert result["created"] == 1
        added = db.add.call_args[0][0]
        assert added.party_name == "Kumar Enterprises"
        assert added.from_godown == "Main Location"

    def test_creates_receipt_note(self):
        db = _db(existing=None)
        txn = {
            "transaction_type": "RECEIPT_NOTE",
            "transaction_number": "RN-3",
            "date": "20260901",
            "narration": "Goods received from Kapoor Suppliers",
            "party": "Kapoor Suppliers",
            "from_godown": "",
            "to_godown": "Main Location",
            "voucher_type_name": "Receipt Note",
            "entries": [
                {"stock_item_name": "Remote", "quantity": 10, "unit": "Nos", "rate": 500, "godown": "Main Location", "inward": True},
            ],
        }
        result = sync_stock_transactions(db, CID, [txn])
        assert result["created"] == 1
        added = db.add.call_args[0][0]
        assert added.transaction_type == "RECEIPT_NOTE"

    def test_creates_rejection_in(self):
        db = _db(existing=None)
        txn = {
            "transaction_type": "REJECTION_IN",
            "transaction_number": "RI-2",
            "date": "20260901",
            "narration": "Goods returned by Kumar",
            "party": "Kumar Enterprises",
            "from_godown": "",
            "to_godown": "Main Location",
            "voucher_type_name": "Rejections In",
            "entries": [
                {"stock_item_name": "Chair", "quantity": 3, "unit": "Nos", "rate": 0, "godown": "Main Location", "inward": True},
            ],
        }
        result = sync_stock_transactions(db, CID, [txn])
        assert result["created"] == 1

    def test_creates_rejection_out(self):
        db = _db(existing=None)
        txn = {
            "transaction_type": "REJECTION_OUT",
            "transaction_number": "RO-1",
            "date": "20260901",
            "narration": "Return defective goods to Kapoor",
            "party": "Kapoor Suppliers",
            "from_godown": "Main Location",
            "to_godown": "",
            "voucher_type_name": "Rejections Out",
            "entries": [
                {"stock_item_name": "Remote", "quantity": 2, "unit": "Nos", "rate": 0, "godown": "Main Location", "inward": False},
            ],
        }
        result = sync_stock_transactions(db, CID, [txn])
        assert result["created"] == 1

    def test_updates_existing_stock_transaction(self):
        existing = MagicMock()
        db = _db(existing=existing)
        result = sync_stock_transactions(db, CID, [self.STOCK_JOURNAL])
        assert result["updated"] == 1
        assert result["created"] == 0
        assert existing.tally_sync_status == "synced"
        assert existing.from_godown == "Main Location"
        assert existing.to_godown == "Chennai"

    def test_skips_missing_transaction_number(self):
        db = _db(existing=None)
        txn = {**self.STOCK_JOURNAL, "transaction_number": ""}
        result = sync_stock_transactions(db, CID, [txn])
        assert result["created"] == 0
        db.add.assert_not_called()

    def test_skips_missing_transaction_type(self):
        db = _db(existing=None)
        txn = {**self.STOCK_JOURNAL, "transaction_type": ""}
        result = sync_stock_transactions(db, CID, [txn])
        assert result["created"] == 0

    def test_date_parsed_correctly(self):
        db = _db(existing=None)
        sync_stock_transactions(db, CID, [self.STOCK_JOURNAL])
        added = db.add.call_args[0][0]
        assert added.transaction_date is not None
        assert added.transaction_date.year == 2026
        assert added.transaction_date.month == 9
        assert added.transaction_date.day == 1


# ─── sync_vouchers ────────────────────────────────────────────────────────────

class TestSyncVouchers:
    """Tests that all 8 accounting voucher types are correctly routed."""

    def _run(self, voucher_type: str, amount: str = "25000"):
        db = MagicMock()
        # All queries return None (no existing record)
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.update.return_value = 0
        db.query.return_value.filter.return_value.all.return_value = []
        return db

    def test_wipe_includes_all_entries_not_just_tally_sync_tagged(self):
        """
        The wipe step must remove ALL invoices/expenses (not only [tally-sync] tagged ones).
        This ensures FinPilot-created entries that no longer exist in TallyPrime are cleaned up.
        Pending and delete_pending entries are preserved.
        """
        db = MagicMock()
        db.query.return_value.filter.return_value.update.return_value = 5
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.all.return_value = []

        sync_vouchers(db, CID, [])

        # The wipe update() must be called (twice — once for Invoice, once for Expense)
        assert db.query.return_value.filter.return_value.update.call_count >= 2

        # Verify the filter does NOT restrict to notes LIKE '[tally-sync]%'
        # (we check by looking at filter call args — none should reference TALLY_TAG)
        all_filter_calls = str(db.query.return_value.filter.call_args_list)
        assert "tally-sync" not in all_filter_calls

    def test_sales_creates_invoice(self):
        db = self._run("Sales")
        from app.models.invoice import Invoice
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Sales", "narration": "Sale to Kumar", "party": "Kumar Enterprises",
             "date": "20260901", "amount": "25000", "voucher_number": "19"},
        ])
        assert result["invoices"] == 1
        assert result["expenses"] == 0
        added = db.add.call_args[0][0]
        assert type(added).__name__ == "Invoice"

    def test_purchase_creates_expense(self):
        db = self._run("Purchase")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Purchase", "narration": "Purchase from Kapoor", "party": "Kapoor Suppliers",
             "date": "20260901", "amount": "18500", "voucher_number": "38"},
        ])
        assert result["expenses"] == 1
        added = db.add.call_args[0][0]
        assert type(added).__name__ == "Expense"
        assert added.category == "Purchase"

    def test_receipt_creates_expense_with_receipt_category(self):
        db = self._run("Receipt")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Receipt", "narration": "Cash received", "party": "Cash",
             "date": "20260901", "amount": "25000", "voucher_number": "19"},
        ])
        assert result["expenses"] == 1
        added = db.add.call_args[0][0]
        assert added.category == "Receipt"

    def test_payment_creates_expense_with_payment_category(self):
        db = self._run("Payment")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Payment", "narration": "Paid to supplier", "party": "Kapoor Suppliers",
             "date": "20260901", "amount": "18500", "voucher_number": "38"},
        ])
        assert result["expenses"] == 1
        added = db.add.call_args[0][0]
        assert added.category == "Payment"

    def test_journal_creates_expense_with_journal_category(self):
        db = self._run("Journal")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Journal", "narration": "Depreciation entry", "party": "",
             "date": "20260901", "amount": "5000", "voucher_number": "JV-1"},
        ])
        assert result["expenses"] == 1
        added = db.add.call_args[0][0]
        assert added.category == "Journal"

    def test_contra_creates_expense_with_contra_category(self):
        db = self._run("Contra")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Contra", "narration": "Cash to bank", "party": "Cash",
             "date": "20260901", "amount": "10000", "voucher_number": "C-1"},
        ])
        assert result["expenses"] == 1
        added = db.add.call_args[0][0]
        assert added.category == "Contra"

    def test_credit_note_creates_expense_with_credit_note_category(self):
        db = self._run("Credit Note")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Credit Note", "narration": "Sales return", "party": "Kumar Enterprises",
             "date": "20260901", "amount": "5000", "voucher_number": "CN-1"},
        ])
        assert result["expenses"] == 1
        added = db.add.call_args[0][0]
        assert added.category == "Credit Note"

    def test_debit_note_creates_expense_with_debit_note_category(self):
        db = self._run("Debit Note")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Debit Note", "narration": "Purchase return", "party": "Kapoor Suppliers",
             "date": "20260901", "amount": "3000", "voucher_number": "DN-1"},
        ])
        assert result["expenses"] == 1
        added = db.add.call_args[0][0]
        assert added.category == "Debit Note"

    def test_stock_journal_skipped_no_monetary_amount(self):
        """Stock Journal has no monetary amount — must not create any voucher."""
        db = self._run("Stock Journal")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Stock Journal", "narration": "Transfer Remote", "party": "Remote",
             "date": "20260901", "amount": "0", "voucher_number": "7"},
        ])
        assert result["invoices"] == 0
        assert result["expenses"] == 0

    def test_zero_amount_skipped(self):
        db = self._run("Sales")
        result = sync_vouchers(db, CID, [
            {"voucher_type": "Sales", "narration": "Empty sale", "party": "Kumar",
             "date": "20260901", "amount": "0", "voucher_number": "X"},
        ])
        assert result["invoices"] == 0


# ─── process_sync_result (integration) ───────────────────────────────────────

class TestProcessSyncResult:
    """Tests the main entry point with the full set of data types."""

    def _make_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.update.return_value = 0
        db.query.return_value.filter.return_value.all.return_value = []
        return db

    def test_processes_all_entity_types(self):
        db = self._make_db()
        result = process_sync_result(db, CID, {
            "ledgers": [{"name": "Cash", "group": "Cash-in-Hand", "closing_balance": "10000"}],
            "vouchers": [
                {"voucher_type": "Sales", "narration": "", "party": "Kumar",
                 "date": "20260901", "amount": "25000", "voucher_number": "19"},
                {"voucher_type": "Purchase", "narration": "", "party": "Kapoor",
                 "date": "20260901", "amount": "18500", "voucher_number": "38"},
                {"voucher_type": "Receipt", "narration": "", "party": "Cash",
                 "date": "20260901", "amount": "5000", "voucher_number": "REC-1"},
            ],
            "stock_items": [{"name": "Remote", "unit": "Nos", "closing_balance": "50 Nos", "closing_rate": "500"}],
            "godowns": [{"name": "Main Location", "parent": None}, {"name": "Chennai", "parent": "Main Location"}],
            "stock_groups": [{"name": "Electronics", "parent": None}],
            "stock_categories": [{"name": "Consumer Electronics", "parent": None}],
            "units": [{"name": "Nos", "symbol": "Nos", "decimal_places": 0}],
            "groups": [{"name": "Indirect Expenses", "parent": None}],
            "voucher_types": [{"name": "GST Bill", "parent": "Sales", "numbering_method": "Automatic", "is_active": True}],
            "stock_transactions": [
                {
                    "transaction_type": "STOCK_JOURNAL",
                    "transaction_number": "7",
                    "date": "20260901",
                    "narration": "Transfer Remote to Chennai",
                    "party": "",
                    "from_godown": "Main Location",
                    "to_godown": "Chennai",
                    "voucher_type_name": "Stock Journal",
                    "entries": [
                        {"stock_item_name": "Remote", "quantity": 5, "unit": "Nos", "rate": 0, "godown": "Main Location", "inward": False},
                        {"stock_item_name": "Remote", "quantity": 5, "unit": "Nos", "rate": 0, "godown": "Chennai", "inward": True},
                    ],
                }
            ],
        })

        # Accounting vouchers
        assert result["imported_invoices"] == 1   # Sales
        assert result["imported_expenses"] == 2   # Purchase + Receipt

        # Masters
        assert result["imported_godowns"] == 2
        assert result["imported_stock_groups"] == 1
        assert result["imported_stock_categories"] == 1
        assert result["imported_units"] == 1
        assert result["imported_groups"] == 1
        assert result["imported_voucher_types"] == 1
        assert result["imported_products"] == 1

        # Stock transactions (NEW)
        assert result["imported_stock_transactions"] == 1

    def test_empty_result_returns_zeros(self):
        db = self._make_db()
        result = process_sync_result(db, CID, {})
        assert result["imported_invoices"] == 0
        assert result["imported_stock_transactions"] == 0
        assert result["imported_stock_categories"] == 0

    def test_stock_transactions_not_double_counted_as_vouchers(self):
        """Stock Journal in vouchers[] must NOT create an accounting entry."""
        db = self._make_db()
        result = process_sync_result(db, CID, {
            "vouchers": [
                # Stock Journal — amount 0, should be skipped in sync_vouchers
                {"voucher_type": "Stock Journal", "narration": "Transfer", "party": "Remote",
                 "date": "20260901", "amount": "0", "voucher_number": "7"},
            ],
            "stock_transactions": [
                {
                    "transaction_type": "STOCK_JOURNAL",
                    "transaction_number": "7",
                    "date": "20260901",
                    "narration": "Transfer Remote",
                    "party": "",
                    "from_godown": "Main Location",
                    "to_godown": "Chennai",
                    "voucher_type_name": "Stock Journal",
                    "entries": [
                        {"stock_item_name": "Remote", "quantity": 5, "unit": "Nos", "rate": 0, "godown": "Chennai", "inward": True},
                    ],
                }
            ],
        })
        # Only the stock_transactions path should fire
        assert result["imported_invoices"] == 0
        assert result["imported_expenses"] == 0
        assert result["imported_stock_transactions"] == 1
