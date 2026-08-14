"""
TallyPrime Sample Data Seeder
Creates realistic Indian business data in TallyPrime via XML/HTTP.

Run: python tally_seed.py
Make sure TallyPrime is open with Sahil_sample company loaded.
"""
import sys
import time
import xml.etree.ElementTree as ET
import httpx

TALLY_URL = "http://localhost:9000"

CUSTOMERS = [
    {"name": "ABC Electronics Pvt Ltd",  "group": "Sundry Debtors", "opening": "0"},
    {"name": "XYZ Trading Company",       "group": "Sundry Debtors", "opening": "0"},
    {"name": "Patel Industries Ltd",      "group": "Sundry Debtors", "opening": "15000"},
    {"name": "Kumar Enterprises",         "group": "Sundry Debtors", "opening": "8500"},
    {"name": "Tech Solutions Pvt Ltd",    "group": "Sundry Debtors", "opening": "0"},
    {"name": "Mehta & Sons",              "group": "Sundry Debtors", "opening": "22000"},
]

VENDORS = [
    {"name": "Office Supplies Hub",       "group": "Sundry Creditors", "opening": "5000"},
    {"name": "Tech Parts Wholesale",      "group": "Sundry Creditors", "opening": "12000"},
    {"name": "Packaging Solutions Co",    "group": "Sundry Creditors", "opening": "0"},
    {"name": "Raw Materials Depot",       "group": "Sundry Creditors", "opening": "0"},
]

LEDGERS = [
    {"name": "Sales Account",            "group": "Sales Accounts",       "opening": "0"},
    {"name": "Purchase Account",         "group": "Purchase Accounts",    "opening": "0"},
    {"name": "HDFC Bank",                "group": "Bank Accounts",         "opening": "250000"},
    {"name": "Cash",                     "group": "Cash-in-Hand",          "opening": "15000"},
    {"name": "GST Output 18%",           "group": "Duties & Taxes",        "opening": "0"},
    {"name": "GST Input 18%",            "group": "Duties & Taxes",        "opening": "0"},
    {"name": "Salary Expenses",          "group": "Indirect Expenses",     "opening": "0"},
    {"name": "Rent Expenses",            "group": "Indirect Expenses",     "opening": "0"},
    {"name": "Office Expenses",          "group": "Indirect Expenses",     "opening": "0"},
]

STOCK_ITEMS = [
    {"name": "Laptop 15 inch",    "group": "Primary", "unit": "Nos",  "rate": "45000"},
    {"name": "Mobile Phone Pro",  "group": "Primary", "unit": "Nos",  "rate": "28000"},
    {"name": "USB-C Cable 2m",    "group": "Primary", "unit": "Nos",  "rate": "450"},
    {"name": "Wireless Mouse",    "group": "Primary", "unit": "Nos",  "rate": "1200"},
    {"name": "Thermal Printer",   "group": "Primary", "unit": "Nos",  "rate": "8500"},
    {"name": "A4 Paper Ream",     "group": "Primary", "unit": "Pcs",  "rate": "350"},
]

DATE = "20260401"   # TallyPrime current date — all vouchers on this date

SALES_VOUCHERS = [
    {"date": DATE, "party": "ABC Electronics Pvt Ltd",
     "items": [{"amount": "90000"}],
     "narration": "Sale of laptops - Invoice FP-001"},
    {"date": DATE, "party": "XYZ Trading Company",
     "items": [{"amount": "88500"}],
     "narration": "Sale of mobile phones - Invoice FP-002"},
    {"date": DATE, "party": "Tech Solutions Pvt Ltd",
     "items": [{"amount": "51000"}],
     "narration": "Sale of equipment - Invoice FP-003"},
    {"date": DATE, "party": "Patel Industries Ltd",
     "items": [{"amount": "17000"}],
     "narration": "Sale of printers - Invoice FP-004"},
    {"date": DATE, "party": "Mehta & Sons",
     "items": [{"amount": "135000"}],
     "narration": "Bulk laptop sale - Invoice FP-005"},
    {"date": DATE, "party": "Kumar Enterprises",
     "items": [{"amount": "13750"}],
     "narration": "Stationery sale - Invoice FP-006"},
]

PURCHASE_VOUCHERS = [
    {"date": DATE, "party": "Tech Parts Wholesale",
     "amount": "65000",
     "narration": "Electronic components - Bill TP-1042"},
    {"date": DATE, "party": "Office Supplies Hub",
     "amount": "12500",
     "narration": "Office supplies - Bill OS-0887"},
    {"date": DATE, "party": "Raw Materials Depot",
     "amount": "38000",
     "narration": "Raw materials - Bill RM-0556"},
    {"date": DATE, "party": "Packaging Solutions Co",
     "amount": "9800",
     "narration": "Packaging material - Bill PS-0234"},
]

PAYMENT_VOUCHERS = [
    {"date": DATE, "party": "Office Supplies Hub",
     "amount": "5000", "from_ledger": "HDFC Bank",
     "narration": "Payment - OS-0887"},
    {"date": DATE, "party": "Salary Expenses",
     "amount": "85000", "from_ledger": "HDFC Bank",
     "narration": "April 2026 salaries"},
    {"date": DATE, "party": "Rent Expenses",
     "amount": "25000", "from_ledger": "HDFC Bank",
     "narration": "Office rent April 2026"},
]


def _post(xml_body: str) -> ET.Element:
    with httpx.Client(timeout=15) as c:
        r = c.post(TALLY_URL, content=xml_body.encode("utf-8"),
                   headers={"Content-Type": "application/xml"})
        r.raise_for_status()
        root = ET.fromstring(r.text)
        err = root.find(".//LINEERROR")
        if err is not None and err.text:
            raise ValueError(f"Tally error: {err.text.strip()}")
        return root


def _result(root: ET.Element) -> tuple[int, int]:
    c = root.find(".//CREATED")
    a = root.find(".//ALTERED")
    return int(c.text) if c is not None and c.text else 0, \
           int(a.text) if a is not None and a.text else 0


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def create_ledger(name: str, group: str, opening: str = "0") -> bool:
    n, g = _esc(name), _esc(group)
    xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <LEDGER NAME="{n}" ACTION="Create">
        <NAME>{n}</NAME>
        <PARENT>{g}</PARENT>
        <OPENINGBALANCE>{opening}</OPENINGBALANCE>
      </LEDGER>
    </TALLYMESSAGE></DATA>
  </BODY>
</ENVELOPE>"""
    try:
        r = _post(xml)
        c, a = _result(r)
        return c + a > 0
    except Exception as e:
        print(f"  Skipped '{name}': {e}")
        return False


def create_stock_item(name: str, group: str, unit: str, rate: str) -> bool:
    # No PARENT field — let Tally use its default root group
    xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <STOCKITEM NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        <BASEUNITS>{unit}</BASEUNITS>
      </STOCKITEM>
    </TALLYMESSAGE></DATA>
  </BODY>
</ENVELOPE>"""
    try:
        r = _post(xml)
        c, a = _result(r)
        return c + a > 0
    except Exception as e:
        print(f"  Skipped stock '{name}': {e}")
        return False


def create_sales_voucher(v: dict) -> bool:
    total = v["items"][0]["amount"]
    party = _esc(v["party"])
    xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER VCHTYPE="Sales" ACTION="Create">
        <DATE>{v['date']}</DATE>
        <NARRATION>{v['narration']}</NARRATION>
        <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{total}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>Sales Account</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{total}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE></DATA>
  </BODY>
</ENVELOPE>"""
    try:
        time.sleep(0.5)   # Tally needs a moment between imports
        r = _post(xml)
        c, a = _result(r)
        return c + a > 0
    except Exception as e:
        print(f"  Skipped sale '{v['narration']}': {e}")
        return False


def create_purchase_voucher(v: dict) -> bool:
    xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER VCHTYPE="Purchase" ACTION="Create">
        <DATE>{v['date']}</DATE>
        <NARRATION>{v['narration']}</NARRATION>
        <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{v['party']}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{v['amount']}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>Purchase Account</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{v['amount']}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE></DATA>
  </BODY>
</ENVELOPE>"""
    try:
        time.sleep(0.5)
        r = _post(xml)
        c, a = _result(r)
        return c + a > 0
    except Exception as e:
        print(f"  Skipped purchase '{v['narration']}': {e}")
        return False


def create_payment_voucher(v: dict) -> bool:
    xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER VCHTYPE="Payment" ACTION="Create">
        <DATE>{v['date']}</DATE>
        <NARRATION>{v['narration']}</NARRATION>
        <VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{v['party']}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{v['amount']}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{v['from_ledger']}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{v['amount']}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE></DATA>
  </BODY>
</ENVELOPE>"""
    try:
        time.sleep(0.5)
        r = _post(xml)
        c, a = _result(r)
        return c + a > 0
    except Exception as e:
        print(f"  Skipped payment '{v['narration']}': {e}")
        return False


def main():
    print("\n" + "=" * 56)
    print("  FinPilot - TallyPrime Data Seeder")
    print("  Company: Sahil_sample")
    print("=" * 56)

    # Check Tally is running
    try:
        with httpx.Client(timeout=5) as c:
            c.get(TALLY_URL)
    except Exception:
        print("\n  ERROR: Cannot connect to TallyPrime on localhost:9000")
        print("  Make sure TallyPrime is open with Sahil_sample loaded.")
        sys.exit(1)

    print("\n[1/5] Creating ledgers (accounts)...")
    ok = 0
    for l in LEDGERS + CUSTOMERS + VENDORS:
        if create_ledger(l["name"], l["group"], l.get("opening", "0")):
            print(f"  + {l['name']}")
            ok += 1
    print(f"  Done: {ok} ledgers created")

    print("\n[2/5] Creating stock items...")
    ok = 0
    for s in STOCK_ITEMS:
        if create_stock_item(s["name"], s["group"], s["unit"], s["rate"]):
            print(f"  + {s['name']}")
            ok += 1
    print(f"  Done: {ok} stock items created")

    print("\n[3/5] Creating sales vouchers...")
    ok = 0
    for v in SALES_VOUCHERS:
        total = sum(int(i["amount"]) for i in v["items"])
        if create_sales_voucher(v):
            print(f"  + {v['narration']} — Rs.{total:,}")
            ok += 1
    print(f"  Done: {ok} sales vouchers created")

    print("\n[4/5] Creating purchase vouchers...")
    ok = 0
    for v in PURCHASE_VOUCHERS:
        if create_purchase_voucher(v):
            print(f"  + {v['narration']} — Rs.{int(v['amount']):,}")
            ok += 1
    print(f"  Done: {ok} purchase vouchers created")

    print("\n[5/5] Creating payment vouchers...")
    ok = 0
    for v in PAYMENT_VOUCHERS:
        if create_payment_voucher(v):
            print(f"  + {v['narration']} — Rs.{int(v['amount']):,}")
            ok += 1
    print(f"  Done: {ok} payment vouchers created")

    print("\n" + "=" * 56)
    print("  Seeding complete!")
    print("  Go to FinPilot -> TallyPrime -> click 'Sync Now'")
    print("  Data will appear in Customers, Transactions etc.")
    print("=" * 56 + "\n")


if __name__ == "__main__":
    main()
