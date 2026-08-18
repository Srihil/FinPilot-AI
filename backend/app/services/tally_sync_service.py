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
from sqlalchemy import func, or_

from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.models.expense import Expense, ExpenseStatus
from app.models.product import Product
from app.models.tally_masters import TallyLedger, TallyStockGroup, TallyStockItem, TallyUnit, TallyGodown, TallyGroup, TallyVoucherType
from app.models.stock_transaction import StockTransaction
from app.models.stock_category import StockCategory

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


def _prune_deleted(
    db: Session,
    model,
    company_id: uuid.UUID,
    tally_keys_present: set,
) -> int:
    """
    Tombstone any record that was previously synced from TallyPrime but is
    no longer present in the latest sync response — meaning it was deleted
    in TallyPrime.  Only touches records with tally_sync_status='synced'
    so FinPilot-created pending/failed records are never accidentally removed.

    Safety: if tally_keys_present is empty we skip pruning entirely — an
    empty response most likely means the connector couldn't fetch that
    category, not that Tally has zero items.
    """
    if not tally_keys_present:
        return 0

    # Deactivate synced records that are either:
    # 1. No longer present in TallyPrime (tally_key not in the fresh set), OR
    # 2. Have a NULL tally_key — these are stale duplicates from before tally_key
    #    was introduced. NULL NOT IN (...) evaluates to NULL in SQL (not TRUE),
    #    so without this explicit OR clause they would never be pruned.
    removed = db.query(model).filter(
        model.company_id == company_id,
        model.is_active == True,
        model.tally_sync_status == "synced",
        or_(
            model.tally_key == None,
            ~model.tally_key.in_(tally_keys_present),
        ),
    ).update({"is_active": False}, synchronize_session=False)

    return removed or 0


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
    removed_ledgers = 0
    now = datetime.now(timezone.utc)
    tally_keys_seen: set = set()

    for ledger in ledgers:
        name = ledger.get("name", "").strip()
        group = ledger.get("group", "").strip()
        closing_balance_raw = ledger.get("closing_balance", "0")
        group_lower = group.lower()

        if not name:
            continue

        # ── Upsert into TallyLedger (all ledgers) ──
        key = _tally_key(company_id, name)
        tally_keys_seen.add(key)
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
            tl.is_active = True
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
    removed_ledgers = _prune_deleted(db, TallyLedger, company_id, tally_keys_seen)
    return {
        "customers": created_customers,
        "vendors": created_vendors,
        "ledgers": created_ledgers,
        "removed_ledgers": removed_ledgers,
    }


# ─── Godowns ──────────────────────────────────────────────────────────────────

def sync_godowns(db: Session, company_id: uuid.UUID, godowns: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    keys_seen: set = set()

    for item in godowns:
        name = item.get("name", "").strip()
        if not name:
            continue
        parent = item.get("parent") or None

        key = _tally_key(company_id, name)
        keys_seen.add(key)
        existing = db.query(TallyGodown).filter(
            TallyGodown.company_id == company_id,
            TallyGodown.tally_key == key,
        ).first()

        if existing:
            existing.parent = parent
            existing.tally_sync_status = "synced"
            existing.synced_at = now
            existing.is_active = True
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
    removed = _prune_deleted(db, TallyGodown, company_id, keys_seen)
    return {"created": created, "updated": updated, "removed": removed}


# ─── Stock Groups ──────────────────────────────────────────────────────────────

def sync_stock_groups(db: Session, company_id: uuid.UUID, stock_groups: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    keys_seen: set = set()

    for item in stock_groups:
        name = item.get("name", "").strip()
        if not name or name.lower() == "primary":
            continue
        parent = item.get("parent") or None
        if parent and parent.lower() == "primary":
            parent = None

        key = _tally_key(company_id, name)
        keys_seen.add(key)
        existing = db.query(TallyStockGroup).filter(
            TallyStockGroup.company_id == company_id,
            TallyStockGroup.tally_key == key,
        ).first()

        if existing:
            existing.parent = parent
            existing.tally_sync_status = "synced"
            existing.synced_at = now
            existing.is_active = True
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
    removed = _prune_deleted(db, TallyStockGroup, company_id, keys_seen)
    return {"created": created, "updated": updated, "removed": removed}


# ─── Units ────────────────────────────────────────────────────────────────────

def sync_units(db: Session, company_id: uuid.UUID, units: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    keys_seen: set = set()

    for item in units:
        name = item.get("name", "").strip()
        if not name:
            continue
        symbol = item.get("symbol") or name
        decimal_places = item.get("decimal_places", 0)
        unit_type = item.get("unit_type", "simple")

        key = _tally_key(company_id, name)
        keys_seen.add(key)
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
            existing.is_active = True
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
    removed = _prune_deleted(db, TallyUnit, company_id, keys_seen)
    return {"created": created, "updated": updated, "removed": removed}


# ─── Account Groups ───────────────────────────────────────────────────────────

def sync_groups(db: Session, company_id: uuid.UUID, groups: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    keys_seen: set = set()

    for item in groups:
        name = item.get("name", "").strip()
        if not name or name.lower() == "primary":
            continue
        parent = item.get("parent") or None
        if parent and parent.lower() == "primary":
            parent = None

        key = _tally_key(company_id, name)
        keys_seen.add(key)
        existing = db.query(TallyGroup).filter(
            TallyGroup.company_id == company_id,
            TallyGroup.tally_key == key,
        ).first()

        if existing:
            existing.parent = parent
            existing.tally_sync_status = "synced"
            existing.synced_at = now
            existing.is_active = True
            existing.source = "tally_sync"
            updated += 1
        else:
            db.add(TallyGroup(
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
    removed = _prune_deleted(db, TallyGroup, company_id, keys_seen)
    return {"created": created, "updated": updated, "removed": removed}


# ─── Voucher Types ────────────────────────────────────────────────────────────

def sync_voucher_types(db: Session, company_id: uuid.UUID, voucher_types: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    keys_seen: set = set()

    for item in voucher_types:
        name = item.get("name", "").strip()
        if not name:
            continue
        parent = item.get("parent") or None
        numbering = item.get("numbering_method", "Automatic")
        is_active_in_tally = item.get("is_active", True)

        key = _tally_key(company_id, name)
        keys_seen.add(key)
        existing = db.query(TallyVoucherType).filter(
            TallyVoucherType.company_id == company_id,
            TallyVoucherType.tally_key == key,
        ).first()

        if existing:
            existing.parent = parent
            existing.numbering_method = numbering
            existing.is_active = is_active_in_tally
            existing.tally_sync_status = "synced"
            existing.synced_at = now
            existing.source = "tally_sync"
            updated += 1
        else:
            db.add(TallyVoucherType(
                company_id=company_id,
                name=name,
                parent=parent,
                numbering_method=numbering,
                tally_key=key,
                source="tally_sync",
                tally_sync_status="synced",
                synced_at=now,
                is_active=is_active_in_tally,
            ))
            created += 1

    db.flush()
    removed = _prune_deleted(db, TallyVoucherType, company_id, keys_seen)
    return {"created": created, "updated": updated, "removed": removed}


# ─── Stock Items → Products ────────────────────────────────────────────────────

def sync_stock_items(db: Session, company_id: uuid.UUID, stock_items: list[dict]) -> dict:
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    keys_seen: set = set()

    for item in stock_items:
        name = item.get("name", "").strip()
        if not name:
            continue
        unit        = item.get("unit", "")
        stock_group = item.get("stock_group") or None   # parent group from TallyPrime

        # Parse closing rate  (format: "500 /Nos" or "500")
        rate_raw = item.get("closing_rate", "0")
        try:
            rate = abs(float(str(rate_raw).split()[0].replace(",", ""))) if rate_raw else 0.0
        except (ValueError, IndexError):
            rate = 0.0

        # Parse closing balance / quantity (format: "50 Nos" or "50")
        qty_raw = item.get("closing_balance", "0")
        try:
            qty = abs(float(str(qty_raw).split()[0].replace(",", ""))) if qty_raw else 0.0
        except (ValueError, IndexError):
            qty = 0.0

        tally_key = f"{company_id}::{name.lower()}"
        keys_seen.add(tally_key)

        existing = db.query(TallyStockItem).filter(
            TallyStockItem.company_id == company_id,
            TallyStockItem.tally_key == tally_key,
        ).first()

        if existing:
            if rate > 0:
                existing.rate = rate
            if unit:
                existing.unit = unit
            if stock_group:
                existing.stock_group = stock_group
            existing.opening_qty = qty
            existing.tally_sync_status = "synced"
            existing.is_active = True
            existing.synced_at = now
            updated += 1
        else:
            db.add(TallyStockItem(
                company_id=company_id,
                name=name,
                stock_group=stock_group,
                unit=unit or None,
                rate=rate,
                opening_qty=qty,
                tally_key=tally_key,
                source="tally_sync",
                tally_sync_status="synced",
                synced_at=now,
                is_active=True,
            ))
            created += 1

    db.flush()
    removed = _prune_deleted(db, TallyStockItem, company_id, keys_seen)
    return {"created": created, "updated": updated, "removed": removed}


# ─── Vouchers → Invoices / Expenses ──────────────────────────────────────────

def sync_vouchers(db: Session, company_id: uuid.UUID, vouchers: list[dict]) -> dict:
    """
    Replace-sync: TallyPrime is the single source of truth.

    Wipes ALL invoices and expenses for this company (except those currently
    in-flight to/from TallyPrime), then reimports every voucher that exists
    in TallyPrime right now.

    After a sync:
    - Entries created from FinPilot AI Create that exist in TallyPrime → come back
    - Entries created from FinPilot that don't exist in TallyPrime → gone
    - TallyPrime-native entries → always present

    States preserved (not wiped):
    - "pending"        — connector is still in the process of creating this in Tally
    - "delete_pending" — connector is in the process of deleting this from Tally
    """
    # ── Step 1: snapshot existing REMOTEIDs before wiping ───────────────────
    # The Day Book (our only source of FP-xxx REMOTEIDs) only returns today's
    # vouchers. For historical entries we save their tally_voucher_ref keyed by
    # the dedup_key stored in notes ("[tally-sync] {dedup_key}") so we can
    # restore it after reimporting — preserving the ability to delete them.
    KEEP_STATUSES = ("pending", "delete_pending")
    TALLY_TAG_PREFIX = TALLY_TAG + " "  # "[tally-sync] "

    remoteid_snapshot: dict[str, str] = {}
    for inv in db.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.is_deleted.is_not(True),
        ~Invoice.tally_sync_status.in_(KEEP_STATUSES),
        Invoice.tally_voucher_ref.isnot(None),
        Invoice.notes.like(f"%{TALLY_TAG}%"),
    ).all():
        notes = inv.notes or ""
        ref = inv.tally_voucher_ref or ""
        if ref and TALLY_TAG_PREFIX in notes:
            key = notes[notes.index(TALLY_TAG_PREFIX) + len(TALLY_TAG_PREFIX):].strip()
            if key:
                remoteid_snapshot[key] = ref

    for exp in db.query(Expense).filter(
        Expense.company_id == company_id,
        Expense.is_deleted.is_not(True),
        ~Expense.tally_sync_status.in_(KEEP_STATUSES),
        Expense.tally_voucher_ref.isnot(None),
        Expense.notes.like(f"%{TALLY_TAG}%"),
    ).all():
        notes = exp.notes or ""
        ref = exp.tally_voucher_ref or ""
        if ref and TALLY_TAG_PREFIX in notes:
            key = notes[notes.index(TALLY_TAG_PREFIX) + len(TALLY_TAG_PREFIX):].strip()
            if key:
                remoteid_snapshot[key] = ref

    # ── Step 2: wipe everything except in-flight jobs ────────────────────────
    db.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.is_deleted.is_not(True),
        ~Invoice.tally_sync_status.in_(KEEP_STATUSES),
    ).update({"is_deleted": True}, synchronize_session=False)

    db.query(Expense).filter(
        Expense.company_id == company_id,
        Expense.is_deleted.is_not(True),
        ~Expense.tally_sync_status.in_(KEEP_STATUSES),
    ).update({"is_deleted": True}, synchronize_session=False)

    db.flush()

    # ── Step 3: reimport fresh from Tally ────────────────────────────────────
    created_invoices = 0
    created_expenses = 0
    inv_counter = 0
    exp_counter = 0
    seen_keys: set[str] = set()

    for v in vouchers:
        vtype     = v.get("voucher_type", "").lower().strip()
        narration = v.get("narration", "").strip()
        party     = v.get("party", "").strip()
        date_str  = v.get("date", "")
        amount_raw = v.get("amount", "0").replace(",", "").strip().lstrip("-")
        vch_no    = v.get("voucher_number", "").strip()
        remoteid  = v.get("voucher_ref", "").strip()

        # Prefer FP-xxx from Day Book (current-day only). Fall back to the
        # pre-wipe snapshot which covers ALL historical vouchers regardless of date.
        fp_remoteid = remoteid if remoteid.startswith("FP-") else ""

        try:
            amount = abs(float(amount_raw)) if amount_raw else 0.0
        except ValueError:
            amount = 0.0

        if amount == 0:
            continue

        # Unique key per Tally voucher (type + voucher number)
        dedup_key = f"{vtype}::{vch_no}" if vch_no else f"{vtype}::{date_str}::{party}::{amount_raw}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        # Restore REMOTEID from pre-wipe snapshot when Day Book didn't have it
        if not fp_remoteid:
            fp_remoteid = remoteid_snapshot.get(dedup_key, "")

        notes_tag     = _tally_id(dedup_key)
        display_label = narration or party or f"Tally {vtype.title()}"

        try:
            if len(date_str) == 8:
                voucher_date = datetime(
                    int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]),
                    tzinfo=timezone.utc,
                )
            else:
                voucher_date = datetime.now(timezone.utc)
        except Exception:
            voucher_date = datetime.now(timezone.utc)

        is_sales       = "sales" in vtype and "order" not in vtype
        is_receipt     = vtype == "receipt"
        is_credit_note = "credit note" in vtype
        is_purchase    = "purchase" in vtype and "order" not in vtype
        is_payment     = vtype == "payment"
        is_debit_note  = "debit note" in vtype
        is_contra      = vtype == "contra"
        is_journal     = "journal" in vtype and "order" not in vtype

        if is_sales:
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
                notes=notes_tag,
                customer_id=customer.id if customer else None,
                tally_sync_status="synced",
                # Prefer the FP- REMOTEID so FinPilot-created vouchers stay deletable after resync
                tally_voucher_ref=fp_remoteid or vch_no or None,
            ))
            created_invoices += 1

        elif is_purchase:
            vendor = _find_by_tally_id(db, Vendor, company_id, party)
            exp_counter += 1
            db.add(Expense(
                company_id=company_id,
                title=display_label,
                category="Purchase",
                expense_date=voucher_date,
                amount=amount,
                tax_amount=0,
                total_amount=amount,
                currency="INR",
                status=ExpenseStatus.APPROVED,
                notes=notes_tag,
                vendor_id=vendor.id if vendor else None,
                tally_sync_status="synced",
                tally_voucher_ref=fp_remoteid or vch_no or None,
            ))
            created_expenses += 1

        elif is_receipt or is_payment or is_credit_note or is_debit_note or is_contra or is_journal:
            vendor = _find_by_tally_id(db, Vendor, company_id, party) if (is_payment or is_debit_note) else None
            customer = _find_by_tally_id(db, Customer, company_id, party) if (is_receipt or is_credit_note) else None
            category = (
                "Receipt"      if is_receipt      else
                "Payment"      if is_payment      else
                "Credit Note"  if is_credit_note  else
                "Debit Note"   if is_debit_note   else
                "Contra"       if is_contra       else
                "Journal"
            )
            exp_counter += 1
            db.add(Expense(
                company_id=company_id,
                title=display_label,
                category=category,
                expense_date=voucher_date,
                amount=amount,
                tax_amount=0,
                total_amount=amount,
                currency="INR",
                status=ExpenseStatus.APPROVED,
                notes=notes_tag,
                vendor_id=vendor.id if vendor else None,
                tally_sync_status="synced",
                tally_voucher_ref=fp_remoteid or vch_no or None,
            ))
            created_expenses += 1

        # Orders / Stock journals → skip

    db.commit()
    return {"invoices": created_invoices, "expenses": created_expenses}


# ─── Stock Categories ────────────────────────────────────────────────────────

def sync_stock_categories(db: Session, company_id: uuid.UUID, categories: list[dict]) -> dict:
    """Upsert stock categories from TallyPrime into FinPilot."""
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    keys_seen: set = set()

    for item in categories:
        name = item.get("name", "").strip()
        if not name or name.lower() == "primary":
            continue
        parent = item.get("parent") or None
        if parent and parent.lower() == "primary":
            parent = None

        key = _tally_key(company_id, name)
        keys_seen.add(key)
        existing = db.query(StockCategory).filter(
            StockCategory.company_id == company_id,
            StockCategory.tally_key == key,
        ).first()

        if existing:
            existing.parent = parent
            existing.tally_sync_status = "synced"
            existing.synced_at = now
            existing.is_active = True
            existing.source = "tally_sync"
            updated += 1
        else:
            db.add(StockCategory(
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

    # Prune stock categories no longer in TallyPrime
    if keys_seen:
        removed = db.query(StockCategory).filter(
            StockCategory.company_id == company_id,
            StockCategory.is_active == True,
            StockCategory.tally_sync_status == "synced",
            ~StockCategory.tally_key.in_(keys_seen),
        ).update({"is_active": False}, synchronize_session=False)
    else:
        removed = 0

    return {"created": created, "updated": updated, "removed": removed}


# ─── Stock Transactions ───────────────────────────────────────────────────────

def sync_stock_transactions(db: Session, company_id: uuid.UUID, txns: list[dict]) -> dict:
    """
    Replace-sync stock transactions from TallyPrime.

    Dedup by transaction_number + company_id. If already present, update it.
    Mark transactions no longer in TallyPrime as inactive.
    """
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)
    seen_numbers: set = set()

    for txn in txns:
        txn_type = txn.get("transaction_type", "")
        vch_no   = (txn.get("transaction_number") or "").strip()
        if not txn_type or not vch_no:
            continue

        seen_numbers.add(vch_no)

        # Parse date
        date_str = txn.get("date", "")
        try:
            if len(date_str) == 8 and date_str.isdigit():
                txn_date = datetime(
                    int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]),
                    tzinfo=timezone.utc,
                )
            else:
                txn_date = None
        except Exception:
            txn_date = None

        entries    = txn.get("entries", [])
        narration  = txn.get("narration", "")
        party      = txn.get("party", "")
        from_gd    = txn.get("from_godown", "")
        to_gd      = txn.get("to_godown", "")

        existing = db.query(StockTransaction).filter(
            StockTransaction.company_id == company_id,
            StockTransaction.transaction_number == vch_no,
        ).first()

        if existing:
            existing.transaction_type   = txn_type
            existing.transaction_date   = txn_date
            existing.narration          = narration or existing.narration
            existing.party_name         = party or existing.party_name
            existing.from_godown        = from_gd or existing.from_godown
            existing.to_godown          = to_gd or existing.to_godown
            existing.entries            = entries
            existing.tally_sync_status  = "synced"
            existing.is_active          = True
            updated += 1
        else:
            db.add(StockTransaction(
                company_id=company_id,
                transaction_number=vch_no,
                transaction_type=txn_type,
                transaction_date=txn_date,
                narration=narration,
                party_name=party or None,
                from_godown=from_gd or None,
                to_godown=to_gd or None,
                entries=entries,
                tally_sync_status="synced",
                is_active=True,
            ))
            created += 1

    db.flush()

    # Tombstone stock transactions no longer present in TallyPrime
    if seen_numbers:
        removed = db.query(StockTransaction).filter(
            StockTransaction.company_id == company_id,
            StockTransaction.is_active == True,
            StockTransaction.tally_sync_status == "synced",
            ~StockTransaction.transaction_number.in_(seen_numbers),
        ).update({"is_active": False}, synchronize_session=False)
    else:
        removed = 0

    return {"created": created, "updated": updated, "removed": removed}


# ─── Main entry point ─────────────────────────────────────────────────────────

def process_sync_result(db: Session, company_id: uuid.UUID, result: dict) -> dict:
    """
    Called after a SYNC_FULL / SYNC_PARTIAL job succeeds.
    Processes all entity types the connector returned.
    """
    ledgers           = result.get("ledgers", [])
    vouchers          = result.get("vouchers", [])
    stock_items       = result.get("stock_items", [])
    godowns           = result.get("godowns", [])
    stock_groups      = result.get("stock_groups", [])
    stock_categories  = result.get("stock_categories", [])
    units             = result.get("units", [])
    groups            = result.get("groups", [])
    voucher_types     = result.get("voucher_types", [])
    stock_txns        = result.get("stock_transactions", [])

    ledger_stats        = {"customers": 0, "vendors": 0, "ledgers": 0}
    voucher_stats       = {"invoices": 0, "expenses": 0}
    stock_item_stats    = {"created": 0, "updated": 0}
    godown_stats        = {"created": 0, "updated": 0}
    stock_group_stats   = {"created": 0, "updated": 0}
    stock_cat_stats     = {"created": 0, "updated": 0}
    unit_stats          = {"created": 0, "updated": 0}
    group_stats         = {"created": 0, "updated": 0}
    voucher_type_stats  = {"created": 0, "updated": 0}
    stock_txn_stats     = {"created": 0, "updated": 0}

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
    if stock_categories:
        stock_cat_stats = sync_stock_categories(db, company_id, stock_categories)
    if units:
        unit_stats = sync_units(db, company_id, units)
    if groups:
        group_stats = sync_groups(db, company_id, groups)
    if voucher_types:
        voucher_type_stats = sync_voucher_types(db, company_id, voucher_types)
    if stock_txns:
        stock_txn_stats = sync_stock_transactions(db, company_id, stock_txns)

    total_removed = (
        ledger_stats.get("removed_ledgers", 0)
        + stock_item_stats.get("removed", 0)
        + godown_stats.get("removed", 0)
        + stock_group_stats.get("removed", 0)
        + stock_cat_stats.get("removed", 0)
        + unit_stats.get("removed", 0)
        + group_stats.get("removed", 0)
        + voucher_type_stats.get("removed", 0)
        + stock_txn_stats.get("removed", 0)
    )

    return {
        "imported_customers":      ledger_stats["customers"],
        "imported_vendors":        ledger_stats["vendors"],
        "imported_ledgers":        ledger_stats["ledgers"],
        "removed_ledgers":         ledger_stats.get("removed_ledgers", 0),
        "imported_invoices":       voucher_stats["invoices"],
        "imported_expenses":       voucher_stats["expenses"],
        "imported_products":       stock_item_stats["created"],
        "updated_products":        stock_item_stats["updated"],
        "removed_products":        stock_item_stats.get("removed", 0),
        "imported_godowns":        godown_stats["created"],
        "updated_godowns":         godown_stats["updated"],
        "removed_godowns":         godown_stats.get("removed", 0),
        "imported_stock_groups":   stock_group_stats["created"],
        "updated_stock_groups":    stock_group_stats["updated"],
        "removed_stock_groups":    stock_group_stats.get("removed", 0),
        "imported_units":          unit_stats["created"],
        "updated_units":           unit_stats["updated"],
        "removed_units":           unit_stats.get("removed", 0),
        "imported_groups":         group_stats["created"],
        "updated_groups":          group_stats["updated"],
        "removed_groups":          group_stats.get("removed", 0),
        "imported_voucher_types":       voucher_type_stats["created"],
        "updated_voucher_types":        voucher_type_stats["updated"],
        "removed_voucher_types":        voucher_type_stats.get("removed", 0),
        "imported_stock_categories":    stock_cat_stats["created"],
        "updated_stock_categories":     stock_cat_stats["updated"],
        "removed_stock_categories":     stock_cat_stats.get("removed", 0),
        "imported_stock_transactions":  stock_txn_stats["created"],
        "updated_stock_transactions":   stock_txn_stats["updated"],
        "removed_stock_transactions":   stock_txn_stats.get("removed", 0),
        "total_removed_from_tally": total_removed,
    }
