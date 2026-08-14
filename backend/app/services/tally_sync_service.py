"""
TallyPrime → FinPilot sync service.
Maps Tally ledgers/vouchers into FinPilot's existing models.

Deduplication: we store the Tally ledger/voucher name in the notes field
prefixed with [tally-sync] so we can find and update rather than duplicate.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.models.expense import Expense, ExpenseStatus

TALLY_TAG = "[tally-sync]"

DEBTOR_GROUPS = {"sundry debtors", "debtors", "trade receivables"}
CREDITOR_GROUPS = {"sundry creditors", "creditors", "trade payables"}


def _tally_id(name: str) -> str:
    return f"{TALLY_TAG} {name}"


def _find_by_tally_id(db: Session, model, company_id: uuid.UUID, tally_name: str):
    tag = _tally_id(tally_name)
    return db.query(model).filter(
        model.company_id == company_id,
        model.notes.like(f"%{tag}%"),
    ).first()


def sync_ledgers(db: Session, company_id: uuid.UUID, ledgers: list[dict]) -> dict:
    """Import Tally ledgers as Customers (Sundry Debtors) or Vendors (Sundry Creditors)."""
    created_customers = 0
    created_vendors = 0

    for ledger in ledgers:
        name = ledger.get("name", "").strip()
        group = ledger.get("group", "").lower().strip()
        if not name or not group:
            continue

        if any(g in group for g in DEBTOR_GROUPS):
            existing = _find_by_tally_id(db, Customer, company_id, name)
            if not existing:
                c = Customer(
                    company_id=company_id,
                    name=name,
                    notes=_tally_id(name),
                    is_active=True,
                )
                db.add(c)
                created_customers += 1
        elif any(g in group for g in CREDITOR_GROUPS):
            existing = _find_by_tally_id(db, Vendor, company_id, name)
            if not existing:
                v = Vendor(
                    company_id=company_id,
                    name=name,
                    notes=_tally_id(name),
                    is_active=True,
                )
                db.add(v)
                created_vendors += 1

    db.flush()
    return {"customers": created_customers, "vendors": created_vendors}


def sync_vouchers(db: Session, company_id: uuid.UUID, vouchers: list[dict]) -> dict:
    """Import Tally vouchers as Invoices (sales) or Expenses (purchases)."""
    created_invoices = 0
    created_expenses = 0
    inv_counter = db.query(Invoice).filter(Invoice.company_id == company_id).count()
    exp_counter = db.query(Expense).filter(Expense.company_id == company_id).count()

    # Track keys seen within this batch — db.add() isn't visible to queries
    # until flush/commit, so we must deduplicate in-memory too.
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

        # Parse date
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
            inv = Invoice(
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
            )
            db.add(inv)
            created_invoices += 1

        elif "purchase" in vtype:
            if dedup_key in seen_expense_keys:
                continue
            if _find_by_tally_id(db, Expense, company_id, dedup_key):
                continue
            seen_expense_keys.add(dedup_key)

            vendor = _find_by_tally_id(db, Vendor, company_id, party)
            exp_counter += 1
            exp = Expense(
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
            )
            db.add(exp)
            created_expenses += 1

    db.commit()
    return {"invoices": created_invoices, "expenses": created_expenses}


def process_sync_result(db: Session, company_id: uuid.UUID, result: dict) -> dict:
    """Entry point called after a SYNC_FULL job succeeds."""
    ledgers = result.get("ledgers", [])
    vouchers = result.get("vouchers", [])

    ledger_stats = {"customers": 0, "vendors": 0}
    voucher_stats = {"invoices": 0, "expenses": 0}

    if ledgers:
        ledger_stats = sync_ledgers(db, company_id, ledgers)

    if vouchers:
        voucher_stats = sync_vouchers(db, company_id, vouchers)

    return {
        "imported_customers": ledger_stats["customers"],
        "imported_vendors": ledger_stats["vendors"],
        "imported_invoices": voucher_stats["invoices"],
        "imported_expenses": voucher_stats["expenses"],
    }
