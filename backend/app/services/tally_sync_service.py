"""
TallyPrime → FinPilot sync service.
Maps Tally data into FinPilot models and the new Tally master tables.

Deduplication strategy:
- Customers/Vendors/Invoices/Expenses: notes field prefixed with [tally-sync]
- TallyLedger/StockGroup/Unit/Godown/Product: tally_key column (company_id::name_lower)
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.models.expense import Expense, ExpenseStatus
from app.models.product import Product
from app.models.tally_masters import TallyLedger, TallyStockGroup, TallyUnit, TallyGodown

TALLY_TAG = "[tally-sync]"
DEBTOR_GROUPS = {"sundry debtors", "debtors", "trade receivables"}
CREDITOR_GROUPS = {"sundry creditors", "creditors", "trade payables"}


# ─── Dedup helpers ────────────────────────────────────────────────────────────

def _tally_id(name: str) -> str:
    return f"{TALLY_TAG} {name}"


def _tally_key(company_id: uuid.UUID, name: str) -> str:
    return f"{company_id}::{name.strip().lower()}"


def _find_by_tally_id(db: Session, model, company_id: uuid.UUID, tally_name: str):
    tag = _tally_id(tally_name)
    return db.query(model).filter(
        model.company_id == company_id,
        model.notes.like(f"%{tag}%"),
    ).first()


# ─── Ledgers → Customers / Vendors + TallyLedger ────────────────────────────

def sync_ledgers(db: Session, company_id: uuid.UUID, ledgers: list[dict]) -> dict:
    """
    Import Tally ledgers into:
    1. Customer table (Sundry Debtors group)
    2. Vendor table (Sundry Creditors group)
    3. TallyLedger table (ALL ledgers, for the Ledger management view)
    """
    created_customers = 0
    created_vendors = 0
    created_ledgers = 0
    now = datetime.now(timezone.utc)

    for ledger in ledgers:
        name = ledger.get("name", "").strip()
        group = ledger.get("group", "").strip()
        closing_balance_raw = ledger.get("closing_balance", "0")
        group_lower = group.lower()

        if not name:
            continue

        # ── Upsert into TallyLedger (all ledgers) ──
        key = _tally_key(company_id, name)
        tl = db.query(TallyLedger).filter(
            TallyLedger.company_id == company_id,
            TallyLedger.tally_key == key,
        ).first()

        try:
            closing_balance = float(str(closing_balance_raw).replace(",", "").lstrip("-")) if closing_balance_raw else 0.0
        except (ValueError, TypeError):
            closing_balance = 0.0

        if tl:
            tl.parent_group = group or tl.parent_group
            tl.closing_balance = closing_balance
            tl.tally_sync_status = "synced"
            tl.synced_at = now
            tl.source = "tally_sync"
        else:
            tl = TallyLedger(
                company_id=company_id,
                name=name,
                parent_group=group,
                opening_balance=0.0,
                closing_balance=closing_balance,
                tally_key=key,
                source="tally_sync",
                tally_sync_status="synced",
                synced_at=now,
                is_active=True,
            )
            db.add(tl)
            created_ledgers += 1

        # ── Map to Customer / Vendor ──
        if any(g in group_lower for g in DEBTOR_GROUPS):
            existing = _find_by_tally_id(db, Customer, company_id, name)
            if not existing:
                db.add(Customer(
                    company_id=company_id,
                    name=name,
                    notes=_tally_id(name),
                    is_active=True,
                ))
                created_customers += 1

        elif any(g in group_lower for g in CREDITOR_GROUPS):
            existing = _find_by_tally_id(db, Vendor, company_id, name)
            if not existing:
                db.add(Vendor(
                    company_id=company_id,
                    name=name,
                    notes=_tally_id(name),
                    is_active=True,
                ))
                created_vendors += 1

    db.flush()
    return {
        "customers": created_customers,
        "vendors": created_vendors,
        "ledgers": created_ledgers,
    }


# ─── Godowns ──────────────────────────────────────────────────────────────────

def sync_godowns(db: Session, company_id: uuid.UUID, godowns: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)

    for item in godowns:
        name = item.get("name", "").strip()
        if not name:
            continue
        parent = item.get("parent") or None

        key = _tally_key(company_id, name)
        existing = db.query(TallyGodown).filter(
            TallyGodown.company_id == company_id,
            TallyGodown.tally_key == key,
        ).first()

        if existing:
            existing.parent = parent
            existing.tally_sync_status = "synced"
            existing.synced_at = now
            existing.source = "tally_sync"
            updated += 1
        else:
            db.add(TallyGodown(
                company_id=company_id,
                name=name,
                parent=parent,
                tally_key=key,
                source="tally_sync",
                tally_sync_status="synced",
                synced_at=now,
                is_active=True,
            ))
            created += 1

    db.flush()
    return {"created": created, "updated": updated}


# ─── Stock Groups ──────────────────────────────────────────────────────────────

def sync_stock_groups(db: Session, company_id: uuid.UUID, stock_groups: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)

    for item in stock_groups:
        name = item.get("name", "").strip()
        if not name or name.lower() == "primary":
            continue
        parent = item.get("parent") or None
        if parent and parent.lower() == "primary":
            parent = None

        key = _tally_key(company_id, name)
        existing = db.query(TallyStockGroup).filter(
            TallyStockGroup.company_id == company_id,
            TallyStockGroup.tally_key == key,
        ).first()

        if existing:
            existing.parent = parent
            existing.tally_sync_status = "synced"
            existing.synced_at = now
            existing.source = "tally_sync"
            updated += 1
        else:
            db.add(TallyStockGroup(
                company_id=company_id,
                name=name,
                parent=parent,
                tally_key=key,
                source="tally_sync",
                tally_sync_status="synced",
                synced_at=now,
                is_active=True,
            ))
            created += 1

    db.flush()
    return {"created": created, "updated": updated}


# ─── Units ────────────────────────────────────────────────────────────────────

def sync_units(db: Session, company_id: uuid.UUID, units: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)

    for item in units:
        name = item.get("name", "").strip()
        if not name:
            continue
        symbol = item.get("symbol") or name
        decimal_places = item.get("decimal_places", 0)
        unit_type = item.get("unit_type", "simple")

        key = _tally_key(company_id, name)
        existing = db.query(TallyUnit).filter(
            TallyUnit.company_id == company_id,
            TallyUnit.tally_key == key,
        ).first()

        if existing:
            existing.symbol = symbol
            existing.decimal_places = decimal_places
            existing.unit_type = unit_type
            existing.tally_sync_status = "synced"
            existing.synced_at = now
            existing.source = "tally_sync"
            updated += 1
        else:
            db.add(TallyUnit(
                company_id=company_id,
                name=name,
                symbol=symbol,
                decimal_places=decimal_places,
                unit_type=unit_type,
                tally_key=key,
                source="tally_sync",
                tally_sync_status="synced",
                synced_at=now,
                is_active=True,
            ))
            created += 1

    db.flush()
    return {"created": created, "updated": updated}


# ─── Stock Items → Products ────────────────────────────────────────────────────

def sync_stock_items(db: Session, company_id: uuid.UUID, stock_items: list[dict]) -> dict:
    created = 0
    updated = 0

    for item in stock_items:
        name = item.get("name", "").strip()
        if not name:
            continue
        unit = item.get("unit", "Nos")

        # Parse closing balance (quantity)
        qty_raw = item.get("closing_balance", "0")
        try:
            qty = abs(float(str(qty_raw).split()[0].replace(",", ""))) if qty_raw else 0.0
        except (ValueError, IndexError):
            qty = 0.0

        # Parse closing rate
        rate_raw = item.get("closing_rate", "0")
        try:
            rate = abs(float(str(rate_raw).split()[0].replace(",", ""))) if rate_raw else 0.0
        except (ValueError, IndexError):
            rate = 0.0

        # Dedup by name (case-insensitive) within company
        existing = db.query(Product).filter(
            Product.company_id == company_id,
            func.lower(Product.name) == name.lower(),
            Product.is_active == True,
        ).first()

        if existing:
            existing.stock_quantity = qty
            existing.selling_price = rate if rate > 0 else existing.selling_price
            if not existing.unit:
                existing.unit = unit
            updated += 1
        else:
            db.add(Product(
                company_id=company_id,
                name=name,
                unit=unit,
                stock_quantity=qty,
                selling_price=rate,
                purchase_price=0.0,
                tax_rate=0.0,
                is_active=True,
            ))
            created += 1

    db.flush()
    return {"created": created, "updated": updated}


# ─── Vouchers → Invoices / Expenses ──────────────────────────────────────────

def sync_vouchers(db: Session, company_id: uuid.UUID, vouchers: list[dict]) -> dict:
    """Import Tally vouchers as Invoices (sales) or Expenses (purchases)."""
    created_invoices = 0
    created_expenses = 0
    inv_counter = db.query(Invoice).filter(Invoice.company_id == company_id).count()
    exp_counter = db.query(Expense).filter(Expense.company_id == company_id).count()

    seen_invoice_keys: set[str] = set()
    seen_expense_keys: set[str] = set()

    for v in vouchers:
        vtype = v.get("voucher_type", "").lower()
        narration = v.get("narration", "").strip()
        party = v.get("party", "").strip()
        amount_raw = v.get("amount", "0").replace(",", "").strip().lstrip("-")
        dedup_key = narration or party
        narration_tag = _tally_id(dedup_key)

        try:
            amount = abs(float(amount_raw)) if amount_raw else 0.0
        except ValueError:
            amount = 0.0

        if amount == 0 or not dedup_key:
            continue

        date_str = v.get("date", "")
        try:
            if len(date_str) == 8:
                voucher_date = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]),
                                        tzinfo=timezone.utc)
            else:
                voucher_date = datetime.now(timezone.utc)
        except Exception:
            voucher_date = datetime.now(timezone.utc)

        if "sales" in vtype:
            if dedup_key in seen_invoice_keys:
                continue
            if _find_by_tally_id(db, Invoice, company_id, dedup_key):
                continue
            seen_invoice_keys.add(dedup_key)

            customer = _find_by_tally_id(db, Customer, company_id, party)
            inv_counter += 1
            db.add(Invoice(
                company_id=company_id,
                invoice_number=f"TALLY-{inv_counter:04d}",
                invoice_type=InvoiceType.SALES,
                status=InvoiceStatus.APPROVED,
                invoice_date=voucher_date,
                due_date=voucher_date,
                subtotal=amount,
                tax_amount=0,
                discount_amount=0,
                total_amount=amount,
                paid_amount=0,
                currency="INR",
                notes=narration_tag,
                customer_id=customer.id if customer else None,
            ))
            created_invoices += 1

        elif "purchase" in vtype:
            if dedup_key in seen_expense_keys:
                continue
            if _find_by_tally_id(db, Expense, company_id, dedup_key):
                continue
            seen_expense_keys.add(dedup_key)

            vendor = _find_by_tally_id(db, Vendor, company_id, party)
            exp_counter += 1
            db.add(Expense(
                company_id=company_id,
                title=narration or f"Tally Purchase from {party}",
                category="Purchase",
                expense_date=voucher_date,
                amount=amount,
                tax_amount=0,
                total_amount=amount,
                currency="INR",
                status=ExpenseStatus.APPROVED,
                notes=narration_tag,
                vendor_id=vendor.id if vendor else None,
            ))
            created_expenses += 1

    db.commit()
    return {"invoices": created_invoices, "expenses": created_expenses}


# ─── Main entry point ─────────────────────────────────────────────────────────

def process_sync_result(db: Session, company_id: uuid.UUID, result: dict) -> dict:
    """
    Called after a SYNC_FULL / SYNC_PARTIAL job succeeds.
    Processes all entity types the connector returned.
    """
    ledgers      = result.get("ledgers", [])
    vouchers     = result.get("vouchers", [])
    stock_items  = result.get("stock_items", [])
    godowns      = result.get("godowns", [])
    stock_groups = result.get("stock_groups", [])
    units        = result.get("units", [])

    ledger_stats      = {"customers": 0, "vendors": 0, "ledgers": 0}
    voucher_stats     = {"invoices": 0, "expenses": 0}
    stock_item_stats  = {"created": 0, "updated": 0}
    godown_stats      = {"created": 0, "updated": 0}
    stock_group_stats = {"created": 0, "updated": 0}
    unit_stats        = {"created": 0, "updated": 0}

    if ledgers:
        ledger_stats = sync_ledgers(db, company_id, ledgers)

    if vouchers:
        voucher_stats = sync_vouchers(db, company_id, vouchers)

    if stock_items:
        stock_item_stats = sync_stock_items(db, company_id, stock_items)

    if godowns:
        godown_stats = sync_godowns(db, company_id, godowns)

    if stock_groups:
        stock_group_stats = sync_stock_groups(db, company_id, stock_groups)

    if units:
        unit_stats = sync_units(db, company_id, units)

    return {
        "imported_customers":    ledger_stats["customers"],
        "imported_vendors":      ledger_stats["vendors"],
        "imported_ledgers":      ledger_stats["ledgers"],
        "imported_invoices":     voucher_stats["invoices"],
        "imported_expenses":     voucher_stats["expenses"],
        "imported_products":     stock_item_stats["created"],
        "updated_products":      stock_item_stats["updated"],
        "imported_godowns":      godown_stats["created"],
        "updated_godowns":       godown_stats["updated"],
        "imported_stock_groups": stock_group_stats["created"],
        "updated_stock_groups":  stock_group_stats["updated"],
        "imported_units":        unit_stats["created"],
        "updated_units":         unit_stats["updated"],
    }
