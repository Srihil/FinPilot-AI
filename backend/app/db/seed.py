"""
Seed script for FinPilot AI demo data.
Creates Acme Manufacturing Pvt. Ltd. with 12 months of realistic financial data.

Run: python -m app.db.seed
"""
from sqlalchemy.orm import Session
from app.db.base import SessionLocal, engine, Base
from app.models.company import Company
from app.models.user import User, UserRole
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.invoice import Invoice, InvoiceItem, InvoiceStatus, InvoiceType
from app.models.expense import Expense, ExpenseStatus, ExpenseCategory
from app.models.payment import Payment, PaymentType, PaymentMethod
from app.models.account import Account, AccountType
from app.models.audit_log import AuditLog, AuditAction
from app.core.security import hash_password
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import random
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

random.seed(42)


def months_ago(n: int, day: int = 1) -> datetime:
    now = datetime.now(timezone.utc)
    return (now - relativedelta(months=n)).replace(day=day, hour=10, minute=0, second=0, microsecond=0)


def days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def run_seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        existing = db.query(Company).filter(Company.name == "Acme Manufacturing Pvt. Ltd.").first()
        if existing:
            logger.info("Seed data already exists. Skipping.")
            return

        logger.info("Creating seed data for Acme Manufacturing Pvt. Ltd. ...")

        # ── Company ──────────────────────────────────────────────────
        company = Company(
            name="Acme Manufacturing Pvt. Ltd.",
            legal_name="Acme Manufacturing Private Limited",
            gst_number="27AABCU9603R1ZX",
            pan_number="AABCU9603R",
            address="Plot 42, MIDC Industrial Area, Andheri East",
            city="Mumbai", state="Maharashtra", country="India", pincode="400093",
            phone="+91 22 6123 4567",
            email="accounts@acmemfg.in",
            currency="INR",
            fiscal_year_start="04-01",
        )
        db.add(company)
        db.flush()
        cid = company.id

        # ── Users ────────────────────────────────────────────────────
        admin = User(company_id=cid, full_name="Rajesh Kumar", email="admin@acmemfg.in",
                     hashed_password=hash_password("Admin@123"), role=UserRole.ADMIN,
                     is_active=True, is_verified=True)
        accountant = User(company_id=cid, full_name="Priya Sharma", email="accountant@acmemfg.in",
                          hashed_password=hash_password("Accountant@123"), role=UserRole.ACCOUNTANT,
                          is_active=True, is_verified=True)
        viewer = User(company_id=cid, full_name="Amit Singh", email="viewer@acmemfg.in",
                      hashed_password=hash_password("Viewer@123"), role=UserRole.VIEWER,
                      is_active=True, is_verified=True)
        db.add_all([admin, accountant, viewer])
        db.flush()

        # ── Customers ────────────────────────────────────────────────
        customers_data = [
            ("TechCorp Solutions Ltd.", "procurement@techcorp.in", "+91 80 4567 8901", "Bengaluru", "Karnataka", "29AABCT3518Q1ZV"),
            ("Global Retail Pvt. Ltd.", "accounts@globalretail.com", "+91 22 2345 6789", "Mumbai", "Maharashtra", "27AABCG4521R1ZT"),
            ("Sunrise Industries", "finance@sunrise.co.in", "+91 40 7890 1234", "Hyderabad", "Telangana", "36AABCS5632T1ZQ"),
            ("Modern Electronics Co.", "purchase@modernelec.in", "+91 11 9876 5432", "Delhi", "Delhi", "07AABCM6741U1ZP"),
            ("Premier Constructions", "billing@premierconstruct.com", "+91 79 3456 7890", "Ahmedabad", "Gujarat", "24AABCP7852V1ZN"),
            ("Rapid Logistics Pvt.", "accounts@rapidlogistics.in", "+91 44 5678 9012", "Chennai", "Tamil Nadu", "33AABCR8963W1ZM"),
            ("Greenfield Agro Ltd.", "finance@greenfield.in", "+91 20 2345 6789", "Pune", "Maharashtra", "27AABCG9074X1ZL"),
            ("Crystal Clear Water", "billing@crystalwater.co.in", "+91 33 3456 7890", "Kolkata", "West Bengal", "19AABCC0185Y1ZK"),
        ]
        customers = []
        for name, email, phone, city, state, gst in customers_data:
            c = Customer(company_id=cid, name=name, email=email, phone=phone,
                         city=city, state=state, country="India",
                         gst_number=gst, payment_terms_days=30, credit_limit=5000000)
            db.add(c)
            customers.append(c)
        db.flush()

        # ── Vendors ──────────────────────────────────────────────────
        vendors_data = [
            ("Steel Industries Corp.", "sales@steelinds.in", "+91 22 1234 5678", "Mumbai", "Maharashtra", "27AABCS1234A1ZV"),
            ("Polymer Suppliers Pvt.", "orders@polymers.in", "+91 44 2345 6789", "Chennai", "Tamil Nadu", "33AABCP2345B1ZU"),
            ("Electronic Components Ltd.", "supply@ecl.co.in", "+91 80 3456 7890", "Bengaluru", "Karnataka", "29AABCE3456C1ZT"),
            ("Office World", "orders@officeworld.in", "+91 22 4567 8901", "Mumbai", "Maharashtra", "27AABCO4567D1ZS"),
            ("QuickFreight Services", "billing@quickfreight.in", "+91 40 5678 9012", "Hyderabad", "Telangana", "36AABCQ5678E1ZR"),
            ("Power Grid Utilities", "accounts@powergrid.in", "+91 11 6789 0123", "Delhi", "Delhi", "07AABCP6789F1ZQ"),
            ("TechSoft Solutions", "invoices@techsoft.in", "+91 20 7890 1234", "Pune", "Maharashtra", "27AABCT7890G1ZP"),
            ("Raw Materials Hub", "sales@rawmaterials.in", "+91 79 8901 2345", "Ahmedabad", "Gujarat", "24AABCR8901H1ZO"),
        ]
        vendors = []
        for name, email, phone, city, state, gst in vendors_data:
            v = Vendor(company_id=cid, name=name, email=email, phone=phone,
                       city=city, state=state, country="India",
                       gst_number=gst, payment_terms_days=30)
            db.add(v)
            vendors.append(v)
        db.flush()

        # ── Products ─────────────────────────────────────────────────
        products_data = [
            ("PART-001", "Steel Bracket Assembly", "Hardware", 450, 720, 18, 1250, 100),
            ("PART-002", "Polymer Housing Unit", "Plastics", 280, 480, 18, 890, 80),
            ("COMP-003", "Electronic Control Module", "Electronics", 1200, 2100, 18, 340, 50),
            ("PART-004", "Aluminium Frame Section", "Hardware", 380, 650, 18, 2100, 150),
            ("COMP-005", "Hydraulic Pump Assembly", "Mechanical", 3500, 5800, 18, 125, 20),
            ("PART-006", "Rubber Seal Kit", "Sealing", 95, 180, 18, 3400, 200),
            ("PART-007", "Stainless Steel Fastener Set", "Hardware", 65, 120, 18, 8900, 500),
            ("COMP-008", "Pneumatic Cylinder Unit", "Mechanical", 2800, 4500, 18, 78, 15),
            ("PART-009", "Copper Wire Harness", "Electrical", 520, 890, 18, 460, 60),
            ("PROD-010", "Complete Machine Assembly", "Finished Goods", 45000, 72000, 18, 12, 3),
        ]
        products = []
        for sku, name, cat, pp, sp, tax, qty, threshold in products_data:
            p = Product(company_id=cid, sku=sku, name=name, category=cat,
                        purchase_price=pp, selling_price=sp, tax_rate=tax,
                        stock_quantity=qty, reorder_threshold=threshold, track_inventory=True)
            db.add(p)
            products.append(p)
        db.flush()

        # ── Accounts ─────────────────────────────────────────────────
        accounts_data = [
            ("Cash & Bank", "1001", AccountType.ASSET),
            ("Accounts Receivable", "1100", AccountType.ASSET),
            ("Inventory", "1200", AccountType.ASSET),
            ("Accounts Payable", "2001", AccountType.LIABILITY),
            ("Sales Revenue", "4001", AccountType.REVENUE),
            ("Cost of Goods Sold", "5001", AccountType.EXPENSE),
            ("Operating Expenses", "5100", AccountType.EXPENSE),
        ]
        for name, code, atype in accounts_data:
            db.add(Account(company_id=cid, name=name, code=code, account_type=atype))

        # ── Invoices (12 months of sales data) ───────────────────────
        inv_num = 1000
        invoice_statuses = [InvoiceStatus.PAID, InvoiceStatus.PAID, InvoiceStatus.SENT,
                            InvoiceStatus.APPROVED, InvoiceStatus.OVERDUE]

        for month in range(12, -1, -1):
            n_invoices = random.randint(8, 15)
            for _ in range(n_invoices):
                customer = random.choice(customers)
                num_items = random.randint(1, 4)
                inv_date = months_ago(month, random.randint(1, 28))
                due_date = inv_date + timedelta(days=30)
                status = InvoiceStatus.PAID if month > 1 else random.choice(invoice_statuses)

                invoice = Invoice(
                    company_id=cid, customer_id=customer.id, created_by=admin.id,
                    invoice_number=f"INV-{inv_num:04d}",
                    invoice_type=InvoiceType.SALES,
                    invoice_date=inv_date, due_date=due_date,
                    currency="INR", status=status,
                    approved_by=admin.id if status in (InvoiceStatus.PAID, InvoiceStatus.APPROVED, InvoiceStatus.SENT) else None,
                    approved_at=inv_date + timedelta(hours=2) if status not in (InvoiceStatus.DRAFT,) else None,
                )
                subtotal = Decimal("0")
                tax_total = Decimal("0")

                for _ in range(num_items):
                    product = random.choice(products[:7])
                    qty = Decimal(str(random.randint(1, 20)))
                    unit_price = Decimal(str(float(product.selling_price) * random.uniform(0.95, 1.05)))
                    tax_rate = Decimal(str(float(product.tax_rate)))
                    line_base = qty * unit_price
                    tax_amount = line_base * tax_rate / 100
                    line_total = line_base + tax_amount
                    subtotal += line_base
                    tax_total += tax_amount
                    invoice.items.append(InvoiceItem(
                        product_id=product.id, description=product.name,
                        quantity=qty, unit_price=unit_price,
                        tax_rate=tax_rate, tax_amount=tax_amount,
                        discount_rate=Decimal("0"), discount_amount=Decimal("0"),
                        line_total=line_total,
                    ))

                invoice.subtotal = subtotal
                invoice.tax_amount = tax_total
                invoice.discount_amount = Decimal("0")
                invoice.total_amount = subtotal + tax_total
                invoice.paid_amount = invoice.total_amount if status == InvoiceStatus.PAID else Decimal("0")
                db.add(invoice)
                inv_num += 1

        # ── Expenses (12 months) ──────────────────────────────────────
        expense_data = [
            ("Electricity Bill", "Utilities", 45000, 8100),
            ("Internet & Telecom", "Utilities", 18000, 3240),
            ("Office Supplies", "Office Supplies", 12000, 2160),
            ("Raw Materials Purchase", "Raw Materials", 285000, 51300),
            ("Machine Maintenance", "Maintenance", 35000, 6300),
            ("Staff Travel Allowance", "Travel", 28000, 5040),
            ("Marketing Campaign", "Marketing", 75000, 13500),
            ("Professional Services", "Professional Services", 55000, 9900),
            ("Shipping & Freight", "Shipping", 42000, 7560),
            ("Insurance Premium", "Insurance", 38000, 6840),
            ("Software Subscriptions", "Software", 22000, 3960),
            ("Warehouse Rent", "Rent", 120000, 21600),
        ]

        for month in range(12, -1, -1):
            for title, category, base_amount, tax_amount in expense_data:
                variance = random.uniform(0.85, 1.20)
                amount = int(base_amount * variance)
                tax = int(tax_amount * variance)
                exp_date = months_ago(month, random.randint(1, 28))
                vendor = random.choice(vendors)
                status = ExpenseStatus.PAID if month > 1 else ExpenseStatus.APPROVED

                e = Expense(
                    company_id=cid, vendor_id=vendor.id, created_by=admin.id,
                    title=title, category=category,
                    expense_date=exp_date, amount=amount, tax_amount=tax,
                    total_amount=amount + tax, currency="INR",
                    status=status,
                    approved_by=admin.id,
                    approved_at=exp_date + timedelta(hours=1),
                )
                db.add(e)

        db.commit()
        logger.info("✅ Seed data created successfully!")
        logger.info("Demo credentials:")
        logger.info("  Admin:      admin@acmemfg.in / Admin@123")
        logger.info("  Accountant: accountant@acmemfg.in / Accountant@123")
        logger.info("  Viewer:     viewer@acmemfg.in / Viewer@123")

    except Exception as e:
        db.rollback()
        logger.error(f"Seed failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
