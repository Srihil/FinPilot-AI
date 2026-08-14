"""
FinPilot — TallyPrime Data Seeder
===================================
Seeds realistic demo ledgers and vouchers DIRECTLY into TallyPrime.
Run: python tally_seeder.py

Requirements:
  - TallyPrime is open with a company loaded
  - HTTP server enabled on port 9000
    (F12 → Configure → Connectivity and timeout configuration
     → Enable HTTP Server → Port 9000)
"""
import sys
import time
import httpx
import xml.etree.ElementTree as ET

TALLY_URL = "http://localhost:9000"
TIMEOUT   = 15


def _post(xml_body: str) -> ET.Element:
    with httpx.Client(timeout=TIMEOUT) as c:
        r = c.post(TALLY_URL, content=xml_body.encode("utf-8"),
                   headers={"Content-Type": "application/xml"})
        r.raise_for_status()
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        raise RuntimeError(f"Bad XML from Tally: {e}\n{r.text[:400]}")
    err = root.find(".//LINEERROR")
    if err is not None and err.text:
        raise RuntimeError(f"Tally error: {err.text.strip()}")
    return root


def check_connection():
    try:
        with httpx.Client(timeout=5) as c:
            c.get(TALLY_URL)
        print("OK TallyPrime reachable on localhost:9000")
    except Exception as e:
        print(f"ERR Cannot reach TallyPrime: {e}")
        print("  → Open TallyPrime, open a company, and enable HTTP server:")
        print("    F12 → Configure → Connectivity → Enable HTTP server, port 9000")
        sys.exit(1)


def create_ledger(name: str, group: str, opening: str = "0") -> bool:
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>All Masters</ID>
  </HEADER>
  <BODY>
    <DESC/>
    <DATA>
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <LEDGER NAME="{name}" ACTION="Create">
          <NAME>{name}</NAME>
          <PARENT>{group}</PARENT>
          <OPENINGBALANCE>{opening}</OPENINGBALANCE>
        </LEDGER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""
    try:
        root = _post(xml)
        created = root.find(".//CREATED")
        altered = root.find(".//ALTERED")
        c = int(created.text) if created is not None and created.text else 0
        a = int(altered.text) if altered is not None and altered.text else 0
        if c > 0:
            print(f"  + Ledger created : {name} [{group}]")
            return True
        elif a > 0:
            print(f"  ~ Ledger exists  : {name} (updated)")
            return True
        else:
            print(f"  ! Ledger skipped : {name} (may already exist)")
            return False
    except RuntimeError as e:
        print(f"  ERR Ledger failed  : {name} — {e}")
        return False


_vctr = {"s": 0, "p": 0}

def create_sales_voucher(date: str, party: str, amount: int,
                         narration: str, sales_ledger: str = "Sales") -> bool:
    _vctr["s"] += 1
    vnum = f"FP-S-{_vctr['s']:03d}"
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
  </HEADER>
  <BODY>
    <DESC/>
    <DATA>
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER REMOTEID="{vnum}" VCHTYPE="Sales" ACTION="Create">
          <DATE>{date}</DATE>
          <VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>
          <NARRATION>{narration}</NARRATION>
          <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>{party}</LEDGERNAME>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
            <AMOUNT>-{amount}</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>{sales_ledger}</LEDGERNAME>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
            <AMOUNT>{amount}</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""
    try:
        root = _post(xml)
        created = root.find(".//CREATED")
        c = int(created.text) if created is not None and created.text else 0
        if c > 0:
            print(f"  + Sales voucher  : {party} Rs.{amount:,}  [{date}]")
            return True
        print(f"  ! Sales voucher skipped: {narration}")
        return False
    except RuntimeError as e:
        print(f"  ERR Sales failed   : {party} — {e}")
        return False


def create_purchase_voucher(date: str, party: str, amount: int,
                             narration: str, purchase_ledger: str = "Purchases") -> bool:
    _vctr["p"] += 1
    vnum = f"FP-P-{_vctr['p']:03d}"
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Vouchers</ID>
  </HEADER>
  <BODY>
    <DESC/>
    <DATA>
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER REMOTEID="{vnum}" VCHTYPE="Purchase" ACTION="Create">
          <DATE>{date}</DATE>
          <VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>
          <NARRATION>{narration}</NARRATION>
          <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>{party}</LEDGERNAME>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
            <AMOUNT>{amount}</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>{purchase_ledger}</LEDGERNAME>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
            <AMOUNT>-{amount}</AMOUNT>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""
    try:
        root = _post(xml)
        created = root.find(".//CREATED")
        c = int(created.text) if created is not None and created.text else 0
        if c > 0:
            print(f"  + Purchase voucher: {party} Rs.{amount:,}  [{date}]")
            return True
        print(f"  ! Purchase voucher skipped: {narration}")
        return False
    except RuntimeError as e:
        print(f"  ERR Purchase failed : {party} — {e}")
        return False


def main():
    print()
    print("=" * 55)
    print("  FinPilot — TallyPrime Data Seeder")
    print("=" * 55)
    print()

    check_connection()
    print()

    # ── Step 0: Ensure Sales / Purchase ledgers exist ────────────
    print("Creating income/expense ledgers...")
    create_ledger("Sales",     "Sales Accounts")
    create_ledger("Purchases", "Purchase Accounts")
    print()

    # ── Step 1: Customer ledgers (Sundry Debtors) ────────────────
    print("Creating customer ledgers (Sundry Debtors)...")
    customers = [
        ("ABC Traders",         "Sundry Debtors"),
        ("XYZ Enterprises",     "Sundry Debtors"),
        ("Sharma and Sons",     "Sundry Debtors"),
        ("Patel Industries",    "Sundry Debtors"),
        ("Mehta Distributors",  "Sundry Debtors"),
        ("Verma Exports",       "Sundry Debtors"),
        ("Singh Electronics",   "Sundry Debtors"),
    ]
    for name, group in customers:
        create_ledger(name, group)
        time.sleep(2)

    print()

    # ── Step 2: Vendor ledgers (Sundry Creditors) ────────────────
    print("Creating vendor ledgers (Sundry Creditors)...")
    vendors = [
        ("Kapoor Suppliers",    "Sundry Creditors"),
        ("Gupta Raw Materials", "Sundry Creditors"),
        ("Agarwal Traders",     "Sundry Creditors"),
        ("Steel Industries Co", "Sundry Creditors"),
        ("National Plastics",   "Sundry Creditors"),
    ]
    for name, group in vendors:
        create_ledger(name, group)
        time.sleep(2)

    print()

    # ── Step 3: Sales vouchers ────────────────────────────────────
    print("Creating sales vouchers...")
    sales = [
        ("20260401", "ABC Traders",        142000, "Sale of electronic components - Inv 001"),
        ("20260408", "XYZ Enterprises",     87500, "Supply of hardware parts - Inv 002"),
        ("20260415", "Sharma and Sons",    215000, "Bulk goods supply - Inv 003"),
        ("20260422", "Patel Industries",    63000, "Monthly supply order - Inv 004"),
        ("20260502", "Mehta Distributors", 178000, "Q1 merchandise supply - Inv 005"),
        ("20260510", "ABC Traders",         95000, "Steel bracket supply - Inv 006"),
        ("20260518", "Verma Exports",      320000, "Export order - Inv 007"),
        ("20260601", "Singh Electronics",  112000, "Circuit board supply - Inv 008"),
        ("20260615", "XYZ Enterprises",     74500, "Spare parts supply - Inv 009"),
        ("20260701", "Sharma and Sons",    189000, "Q2 goods supply - Inv 010"),
        ("20260715", "Patel Industries",   255000, "Hydraulic units - Inv 011"),
        ("20260801", "ABC Traders",         48000, "Aluminium supply - Inv 012"),
    ]
    for date, party, amount, narration in sales:
        create_sales_voucher(date, party, amount, narration)
        time.sleep(2)

    print()

    # ── Step 4: Purchase vouchers ─────────────────────────────────
    print("Creating purchase vouchers...")
    purchases = [
        ("20260403", "Kapoor Suppliers",     85000, "Raw material purchase - Bill KS/2026/101"),
        ("20260410", "Gupta Raw Materials",  120000, "Aluminium rods purchase - Bill GRM/2026/45"),
        ("20260420", "Steel Industries Co",  195000, "Steel sheets - Bill SI/2026/78"),
        ("20260505", "Agarwal Traders",       45000, "Hardware components - Bill AT/2026/33"),
        ("20260512", "National Plastics",     38000, "Plastic parts purchase - Bill NP/2026/22"),
        ("20260601", "Kapoor Suppliers",      92000, "Q2 raw materials - Bill KS/2026/156"),
        ("20260620", "Gupta Raw Materials",   67000, "Copper wire purchase - Bill GRM/2026/89"),
        ("20260705", "Steel Industries Co",  145000, "Steel rods batch - Bill SI/2026/112"),
        ("20260720", "Agarwal Traders",       55000, "Fasteners purchase - Bill AT/2026/67"),
        ("20260801", "National Plastics",     72000, "Polymer supply - Bill NP/2026/48"),
    ]
    for date, party, amount, narration in purchases:
        create_purchase_voucher(date, party, amount, narration)
        time.sleep(2)

    print()
    print("=" * 55)
    print("  Seeding complete!")
    print()
    print("  Created in TallyPrime:")
    print(f"   - {len(customers)} customer ledgers (Sundry Debtors)")
    print(f"   - {len(vendors)} vendor ledgers (Sundry Creditors)")
    print(f"   - {len(sales)} sales vouchers")
    print(f"   - {len(purchases)} purchase vouchers")
    print()
    print("  Next: Go to finpilot-frontend-vbdf.onrender.com")
    print("        -> TallyPrime page -> click Sync Now")
    print("        All this data will appear on your website.")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()
