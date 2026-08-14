"""
TallyPrime HTTP/XML client.

Communicates with TallyPrime's built-in HTTP server (localhost:9000).
All XML is constructed here — the LLM / cloud backend never sends raw XML.

TallyPrime XML API reference:
  - Enable: F12 → Configure → Connectivity → Enable HTTP server
  - Endpoint: POST http://localhost:9000
  - Content-Type: application/xml (or text/xml)
  - Body: TDL XML request
"""
import logging
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# XXE protection: we use defusedxml when parsing, never when building
try:
    from defusedxml import ElementTree as SafeET
    SAFE_PARSE = SafeET.fromstring
except ImportError:
    # fallback: standard library — safe enough for data we requested ourselves
    SAFE_PARSE = ET.fromstring


class TallyError(Exception):
    pass


class TallyClient:
    def __init__(self, host: str = "localhost", port: int = 9000, timeout: int = 15):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout

    def _post_xml(self, xml_body: str) -> str:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self.base_url,
                    content=xml_body.encode("utf-8"),
                    headers={"Content-Type": "application/xml"},
                )
                resp.raise_for_status()
                return resp.text
        except httpx.ConnectError:
            raise TallyError(
                f"Cannot connect to TallyPrime on {self.base_url}. "
                "Ensure TallyPrime is running and the HTTP server is enabled "
                "(F12 → Configure → Connectivity)."
            )
        except httpx.TimeoutException:
            raise TallyError("TallyPrime request timed out. Is a company file open?")
        except httpx.HTTPStatusError as e:
            raise TallyError(f"TallyPrime returned HTTP {e.response.status_code}")

    def _parse_response(self, xml_text: str) -> ET.Element:
        try:
            root = SAFE_PARSE(xml_text)
        except ET.ParseError as e:
            raise TallyError(f"Invalid XML from TallyPrime: {e}")
        lineerror = root.find(".//LINEERROR")
        if lineerror is not None and lineerror.text:
            raise TallyError(f"TallyPrime error: {lineerror.text.strip()}")
        return root

    # ── Availability check ───────────────────────────────────────────────────

    def is_reachable(self) -> bool:
        try:
            with httpx.Client(timeout=5) as client:
                client.get(self.base_url)
            return True
        except Exception:
            return False

    # ── Company info ─────────────────────────────────────────────────────────

    def get_active_company(self) -> Optional[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>List of Companies</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            raw = self._post_xml(xml)
            root = self._parse_response(raw)
            name = self._extract_company_name(root)
            return {"name": name} if name else None
        except TallyError:
            return None

    def _extract_company_name(self, root: ET.Element) -> Optional[str]:
        """Try multiple XML paths used by different TallyPrime versions/EDU."""
        # Only look inside actual <COMPANY> elements — avoids numeric fields
        # like <FORCECOMPANYRELOAD>0</FORCECOMPANYRELOAD>
        for company_el in root.findall(".//COMPANY"):
            # Priority order for name fields
            for tag in ("BASICCOMPANYNAME", "NAME", "COMPANYNAME"):
                el = company_el.find(tag)
                if el is not None and el.text:
                    val = el.text.strip()
                    if val and not val.lstrip("-").isdigit():
                        return val
            # NAME.LIST/NAME pattern (TallyPrime newer builds)
            nl = company_el.find("NAME.LIST/NAME")
            if nl is not None and nl.text:
                val = nl.text.strip()
                if val and not val.lstrip("-").isdigit():
                    return val

        # Last resort: look for BASICCOMPANYNAME anywhere in the tree
        el = root.find(".//BASICCOMPANYNAME")
        if el is not None and el.text and el.text.strip():
            return el.text.strip()

        return None

    # ── Ledgers ──────────────────────────────────────────────────────────────

    def get_ledgers(self, company: str = "") -> list[dict]:
        xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>List of Ledgers</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        ledgers = []
        for item in root.findall(".//LEDGER"):
            name = item.find("NAME")
            group = item.find("PARENT")
            balance = item.find("CLOSINGBALANCE")
            ledgers.append({
                "name": name.text.strip() if name is not None and name.text else "",
                "group": group.text.strip() if group is not None and group.text else "",
                "closing_balance": balance.text.strip() if balance is not None and balance.text else "0",
            })
        return ledgers

    # ── Vouchers (all types) ──────────────────────────────────────────────────

    def get_vouchers(self, from_date: str = "", to_date: str = "") -> list[dict]:
        date_filter = ""
        if from_date:
            date_filter += f"<SVFROMDATE>{from_date}</SVFROMDATE>"
        if to_date:
            date_filter += f"<SVTODATE>{to_date}</SVTODATE>"
        xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>Voucher Register</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        {date_filter}
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        vouchers = []
        for v in root.findall(".//VOUCHER"):
            date = v.find("DATE")
            vtype = v.find("VOUCHERTYPENAME")
            narration = v.find("NARRATION")
            amount = v.find(".//AMOUNT")
            party = v.find(".//PARTYLEDGERNAME")
            vouchers.append({
                "date": date.text.strip() if date is not None and date.text else "",
                "voucher_type": vtype.text.strip() if vtype is not None and vtype.text else "",
                "party": party.text.strip() if party is not None and party.text else "",
                "amount": amount.text.strip() if amount is not None and amount.text else "0",
                "narration": narration.text.strip() if narration is not None and narration.text else "",
            })
        return vouchers

    # ── Sales vouchers ────────────────────────────────────────────────────────

    def get_sales(self, from_date: str = "", to_date: str = "") -> list[dict]:
        all_vouchers = self.get_vouchers(from_date, to_date)
        return [v for v in all_vouchers if "Sales" in v.get("voucher_type", "")]

    # ── Purchase vouchers ─────────────────────────────────────────────────────

    def get_purchases(self, from_date: str = "", to_date: str = "") -> list[dict]:
        all_vouchers = self.get_vouchers(from_date, to_date)
        return [v for v in all_vouchers if "Purchase" in v.get("voucher_type", "")]

    # ── Receivables / Payables ────────────────────────────────────────────────

    def get_receivables(self) -> list[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>Outstanding Receivables</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            raw = self._post_xml(xml)
            root = self._parse_response(raw)
            return self._parse_outstanding(root)
        except TallyError as e:
            logger.warning("get_receivables: %s", e)
            return []

    def get_payables(self) -> list[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>Outstanding Payables</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            raw = self._post_xml(xml)
            root = self._parse_response(raw)
            return self._parse_outstanding(root)
        except TallyError as e:
            logger.warning("get_payables: %s", e)
            return []

    def _parse_outstanding(self, root: ET.Element) -> list[dict]:
        items = []
        for el in root.findall(".//*[@NAME]"):
            amount = el.find("AMOUNT")
            if amount is not None:
                items.append({
                    "party": el.get("NAME", ""),
                    "amount": amount.text.strip() if amount.text else "0",
                })
        return items

    # ── Stock items ───────────────────────────────────────────────────────────

    def get_stock_items(self) -> list[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>List of Stock Items</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        items = []
        for item in root.findall(".//STOCKITEM"):
            name = item.find("NAME")
            unit = item.find("BASEUNITS")
            qty = item.find("CLOSINGBALANCE")
            rate = item.find("CLOSINGRATE")
            items.append({
                "name": name.text.strip() if name is not None and name.text else "",
                "unit": unit.text.strip() if unit is not None and unit.text else "",
                "closing_balance": qty.text.strip() if qty is not None and qty.text else "0",
                "closing_rate": rate.text.strip() if rate is not None and rate.text else "0",
            })
        return items

    # ── Write: Create sales voucher ───────────────────────────────────────────

    def create_sales_voucher(self, payload: dict) -> dict:
        """
        payload keys: date, party_ledger, sales_ledger, amount, narration, items (optional)
        """
        date = payload.get("date", "")
        party = payload.get("party_ledger", "")
        sales_ledger = payload.get("sales_ledger", "Sales Account")
        amount = payload.get("amount", "0")
        narration = payload.get("narration", "")

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
        <VOUCHER REMOTEID="" VCHTYPE="Sales" ACTION="Create">
          <DATE>{date}</DATE>
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
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        altered = root.find(".//ALTERED")
        return {
            "created": int(created.text) if created is not None and created.text else 0,
            "altered": int(altered.text) if altered is not None and altered.text else 0,
        }

    # ── Write: Create purchase voucher ────────────────────────────────────────

    def create_purchase_voucher(self, payload: dict) -> dict:
        date = payload.get("date", "")
        party = payload.get("party_ledger", "")
        purchase_ledger = payload.get("purchase_ledger", "Purchase Account")
        amount = payload.get("amount", "0")
        narration = payload.get("narration", "")

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
        <VOUCHER REMOTEID="" VCHTYPE="Purchase" ACTION="Create">
          <DATE>{date}</DATE>
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
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    # ── Write: Create ledger ──────────────────────────────────────────────────

    def create_ledger(self, payload: dict) -> dict:
        name = payload.get("name", "")
        group = payload.get("group", "Sundry Debtors")
        opening_balance = payload.get("opening_balance", "0")

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
          <OPENINGBALANCE>{opening_balance}</OPENINGBALANCE>
        </LEDGER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}
