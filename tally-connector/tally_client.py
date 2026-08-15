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
import time
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

    @staticmethod
    def _sanitize_xml(xml_text: str) -> str:
        import re
        # TallyPrime sometimes emits control characters (&#x00;–&#x1F; minus TAB/LF/CR)
        # that are illegal in XML 1.0 — strip them before parsing.
        # Remove numeric character references to invalid code points
        xml_text = re.sub(r'&#x[0-8B-CE-Fb-ce-f];', '', xml_text)
        xml_text = re.sub(r'&#x1[0-9A-Fa-f];', '', xml_text)
        xml_text = re.sub(r'&#\d{1,5};',
                          lambda m: '' if int(m.group()[2:-1]) in range(0, 9) or
                          int(m.group()[2:-1]) in range(11, 13) or
                          int(m.group()[2:-1]) in range(14, 32) else m.group(),
                          xml_text)
        # Remove literal control characters
        xml_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', xml_text)
        return xml_text

    def _parse_response(self, xml_text: str) -> ET.Element:
        xml_text = self._sanitize_xml(xml_text)
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
        # Inline TDL collection with explicit FETCH so PARENT is returned as a child
        # element. The built-in "List of Ledgers" only gives LANGUAGENAME.LIST and
        # no PARENT field, so we can't determine the ledger group without this.
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP Ledgers</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP Ledgers" ISMODIFY="No">
            <TYPE>Ledger</TYPE>
            <FETCH>NAME,PARENT,CLOSINGBALANCE</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        ledgers = []
        for item in root.findall(".//LEDGER"):
            # Name is the NAME attribute on <LEDGER>, not a child <NAME> element
            name = (item.get("NAME") or "").strip()
            group_el = item.find("PARENT")
            balance_el = item.find("CLOSINGBALANCE")
            group = group_el.text.strip() if group_el is not None and group_el.text else ""
            balance = balance_el.text.strip() if balance_el is not None and balance_el.text else "0"
            if name and group:
                ledgers.append({"name": name, "group": group, "closing_balance": balance})
        return ledgers

    # ── Vouchers (all types) ──────────────────────────────────────────────────

    def get_vouchers(self, from_date: str = "", to_date: str = "") -> list[dict]:
        # Day Book (TYPE=Data) only returns vouchers in TallyPrime's CURRENT PERIOD
        # setting, missing everything outside that window even with explicit dates.
        # TDL inline collection with TYPE=Voucher returns ALL vouchers regardless of
        # the active period. BELONGSTO=Yes makes SVFROMDATE/SVTODATE work correctly.
        date_vars = ""
        if from_date:
            date_vars += f"\n        <SVFROMDATE>{from_date}</SVFROMDATE>"
        if to_date:
            date_vars += f"\n        <SVTODATE>{to_date}</SVTODATE>"

        xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP Vouchers</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP Vouchers" ISMODIFY="No">
            <TYPE>Voucher</TYPE>
            <BELONGSTO>Yes</BELONGSTO>
            <FETCH>DATE,VOUCHERTYPENAME,NARRATION,PARTYLEDGERNAME,ALLLEDGERENTRIES.LIST</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>{date_vars}
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        vouchers = []
        for v in root.findall(".//VOUCHER"):
            date_el      = v.find("DATE")
            vtype_el     = v.find("VOUCHERTYPENAME")
            narration_el = v.find("NARRATION")
            party_el     = v.find("PARTYLEDGERNAME")

            # Amount: try ledger list → any descendant AMOUNT → default 0
            amount_raw = "0"
            for path in (".//ALLLEDGERENTRIES.LIST/AMOUNT", ".//AMOUNT"):
                el = v.find(path)
                if el is not None and el.text and el.text.strip():
                    amount_raw = el.text.strip()
                    break

            vouchers.append({
                "date":         date_el.text.strip()      if date_el      is not None and date_el.text      else "",
                "voucher_type": vtype_el.text.strip()     if vtype_el     is not None and vtype_el.text     else "",
                "party":        party_el.text.strip()     if party_el     is not None and party_el.text     else "",
                "amount":       amount_raw.lstrip("-"),
                "narration":    narration_el.text.strip() if narration_el is not None and narration_el.text else "",
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
        # Inline TDL: collect Sundry Debtors ledgers with outstanding balance
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP Receivables</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP Receivables" ISMODIFY="No">
            <TYPE>Ledger</TYPE>
            <FILTER>IsDebtorLedger</FILTER>
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="IsDebtorLedger">
            $$InList:$Parent:"Sundry Debtors":"Debtors":"Trade Receivables"
          </SYSTEM>
        </TDLMESSAGE>
      </TDL>
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
        # Inline TDL: collect Sundry Creditors ledgers with outstanding balance
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP Payables</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP Payables" ISMODIFY="No">
            <TYPE>Ledger</TYPE>
            <FILTER>IsCreditorLedger</FILTER>
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="IsCreditorLedger">
            $$InList:$Parent:"Sundry Creditors":"Creditors":"Trade Payables"
          </SYSTEM>
        </TDLMESSAGE>
      </TDL>
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

    @staticmethod
    def _vch_id() -> str:
        """Generate a unique voucher remote ID."""
        return f"FP-{int(time.time() * 1000) % 100000000:08d}"

    # ── Read: Godowns ─────────────────────────────────────────────────────────

    def get_godowns(self) -> list[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP Godowns</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP Godowns" ISMODIFY="No">
            <TYPE>Godown</TYPE>
            <FETCH>NAME,PARENT</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            raw = self._post_xml(xml)
            root = self._parse_response(raw)
            godowns = []
            for item in root.findall(".//GODOWN"):
                name = (item.get("NAME") or "").strip()
                parent_el = item.find("PARENT")
                parent = parent_el.text.strip() if parent_el is not None and parent_el.text else ""
                if name:
                    godowns.append({"name": name, "parent": parent or None})
            return godowns
        except TallyError as e:
            logger.warning("get_godowns: %s", e)
            return []

    # ── Read: Stock Groups ────────────────────────────────────────────────────

    def get_stock_groups(self) -> list[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP StockGroups</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP StockGroups" ISMODIFY="No">
            <TYPE>Stockgroup</TYPE>
            <FETCH>NAME,PARENT</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            raw = self._post_xml(xml)
            root = self._parse_response(raw)
            groups = []
            for item in root.findall(".//STOCKGROUP"):
                name = (item.get("NAME") or "").strip()
                parent_el = item.find("PARENT")
                parent = parent_el.text.strip() if parent_el is not None and parent_el.text else ""
                # Skip the implicit root group "Primary"
                if name and name.lower() != "primary":
                    groups.append({"name": name, "parent": parent if parent and parent.lower() != "primary" else None})
            return groups
        except TallyError as e:
            logger.warning("get_stock_groups: %s", e)
            return []

    # ── Read: Units ───────────────────────────────────────────────────────────

    def get_units(self) -> list[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP Units</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP Units" ISMODIFY="No">
            <TYPE>Unit</TYPE>
            <FETCH>NAME,ORIGINALNAME,DECIMALPLACES,UOMTYPE</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            raw = self._post_xml(xml)
            root = self._parse_response(raw)
            units = []
            for item in root.findall(".//UNIT"):
                name = (item.get("NAME") or "").strip()
                sym_el = item.find("ORIGINALNAME")
                dec_el = item.find("DECIMALPLACES")
                typ_el = item.find("UOMTYPE")
                symbol = sym_el.text.strip() if sym_el is not None and sym_el.text else name
                decimals = int(dec_el.text.strip()) if dec_el is not None and dec_el.text and dec_el.text.strip().isdigit() else 0
                unit_type = (typ_el.text.strip().lower() if typ_el is not None and typ_el.text else "simple")
                if name:
                    units.append({"name": name, "symbol": symbol, "decimal_places": decimals, "unit_type": unit_type})
            return units
        except TallyError as e:
            logger.warning("get_units: %s", e)
            return []

    # ── Delete: Master records ────────────────────────────────────────────────

    def _delete_master(self, tag: str, name: str) -> dict:
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <{tag} NAME="{name}" ACTION="Delete"></{tag}>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        deleted = root.find(".//DELETED")
        errors = root.find(".//LINEERROR")
        if errors is not None and errors.text:
            raise TallyError(f"TallyPrime refused delete: {errors.text.strip()}")
        return {"deleted": int(deleted.text) if deleted is not None and deleted.text else 0}

    def delete_ledger(self, payload: dict) -> dict:
        return self._delete_master("LEDGER", payload.get("name", ""))

    def delete_stock_group(self, payload: dict) -> dict:
        return self._delete_master("STOCKGROUP", payload.get("name", ""))

    def delete_unit(self, payload: dict) -> dict:
        return self._delete_master("UNIT", payload.get("name", ""))

    def delete_godown(self, payload: dict) -> dict:
        return self._delete_master("GODOWN", payload.get("name", ""))

    def delete_stock_item(self, payload: dict) -> dict:
        return self._delete_master("STOCKITEM", payload.get("name", ""))

    # ── Write: Create sales voucher ───────────────────────────────────────────

    def create_sales_voucher(self, payload: dict) -> dict:
        """payload: date (YYYYMMDD), party_ledger, sales_ledger, amount, narration"""
        date          = payload.get("date", "")
        party         = payload.get("party_ledger", "")
        sales_ledger  = payload.get("sales_ledger", "Sales")
        amount        = str(payload.get("amount", "0")).lstrip("-")
        narration     = payload.get("narration", "")
        vnum          = payload.get("voucher_number") or self._vch_id()

        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="Sales" ACTION="Create">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
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
  </DATA></BODY>
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
        """payload: date (YYYYMMDD), party_ledger, purchase_ledger, amount, narration"""
        date             = payload.get("date", "")
        party            = payload.get("party_ledger", "")
        purchase_ledger  = payload.get("purchase_ledger", "Purchases")
        amount           = str(payload.get("amount", "0")).lstrip("-")
        narration        = payload.get("narration", "")
        vnum             = payload.get("voucher_number") or self._vch_id()

        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="Purchase" ACTION="Create">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
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
  </DATA></BODY>
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

    # ── Write: Create stock item ──────────────────────────────────────────────

    def create_stock_item(self, payload: dict) -> dict:
        name = payload.get("name", "")
        unit = payload.get("unit", "Nos")
        rate = str(payload.get("rate", payload.get("selling_price", "0")))
        group = payload.get("stock_group", "Primary")

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
        <STOCKITEM NAME="{name}" ACTION="Create">
          <NAME>{name}</NAME>
          <PARENT>{group}</PARENT>
          <BASEUNITS>{unit}</BASEUNITS>
        </STOCKITEM>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    # ── Write: Accounting master — Group ──────────────────────────────────────

    def create_group(self, payload: dict) -> dict:
        """Create an account Group (e.g., under 'Current Assets')."""
        name   = payload.get("name", "")
        parent = payload.get("parent", "Capital Account")
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <GROUP NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        <PARENT>{parent}</PARENT>
      </GROUP>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    # ── Write: Inventory Masters ──────────────────────────────────────────────

    def create_stock_group(self, payload: dict) -> dict:
        name   = payload.get("name", "")
        # Empty parent means top-level under the implicit root; "Primary" is the Tally
        # root stock group but referencing it by name fails in EDU/some versions.
        parent = payload.get("parent", "")
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <STOCKGROUP NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        <PARENT>{parent}</PARENT>
      </STOCKGROUP>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_unit(self, payload: dict) -> dict:
        name     = payload.get("name", "Nos").strip()
        # Tally requires the symbol (ORIGINALNAME) to be a short abbreviation with no
        # spaces — e.g. "Nos", "Kgs", "Pcs". Strip spaces and cap at 8 chars.
        raw_sym  = payload.get("symbol", name).strip()
        symbol   = raw_sym.replace(" ", "")[:8] or name.replace(" ", "")[:8] or "Nos"
        decimals = payload.get("decimal_places", "0")
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <UNIT NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        <ORIGINALNAME>{symbol}</ORIGINALNAME>
        <DECIMALPLACES>{decimals}</DECIMALPLACES>
        <UOMTYPE>Simple</UOMTYPE>
      </UNIT>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_godown(self, payload: dict) -> dict:
        name   = payload.get("name", "")
        parent = payload.get("parent", "Main Location")
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <GODOWN NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        <PARENT>{parent}</PARENT>
      </GODOWN>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    # ── Write: Vouchers (Receipt, Payment, Journal, Credit/Debit Note, Contra) ─

    def create_receipt_voucher(self, payload: dict) -> dict:
        """Money received FROM customer INTO bank/cash account."""
        date      = payload.get("date", "")
        party     = payload.get("party_ledger", "")
        account   = payload.get("account_ledger", "Cash")
        amount    = str(payload.get("amount", "0")).lstrip("-")
        narration = payload.get("narration", "Receipt")
        vnum      = self._vch_id()
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="Receipt" ACTION="Create">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
        <VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{account}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_payment_voucher(self, payload: dict) -> dict:
        """Money paid TO vendor FROM bank/cash account."""
        date      = payload.get("date", "")
        party     = payload.get("party_ledger", "")
        account   = payload.get("account_ledger", "Cash")
        amount    = str(payload.get("amount", "0")).lstrip("-")
        narration = payload.get("narration", "Payment")
        vnum      = self._vch_id()
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="Payment" ACTION="Create">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
        <VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{account}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_journal_voucher(self, payload: dict) -> dict:
        """General journal entry: dr_ledger Dr, cr_ledger Cr."""
        date      = payload.get("date", "")
        dr_ledger = payload.get("dr_ledger", "")
        cr_ledger = payload.get("cr_ledger", "")
        amount    = str(payload.get("amount", "0")).lstrip("-")
        narration = payload.get("narration", "Journal Entry")
        vnum      = self._vch_id()
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="Journal" ACTION="Create">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
        <VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{dr_ledger}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{cr_ledger}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_credit_note(self, payload: dict) -> dict:
        """Sales return: reduces receivable, reduces sales."""
        date          = payload.get("date", "")
        party         = payload.get("party_ledger", "")
        sales_ledger  = payload.get("sales_ledger", "Sales")
        amount        = str(payload.get("amount", "0")).lstrip("-")
        narration     = payload.get("narration", "Sales Return")
        vnum          = self._vch_id()
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="Credit Note" ACTION="Create">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
        <VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>Credit Note</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{sales_ledger}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_debit_note(self, payload: dict) -> dict:
        """Purchase return: reduces payable, reduces purchases."""
        date             = payload.get("date", "")
        party            = payload.get("party_ledger", "")
        purchase_ledger  = payload.get("purchase_ledger", "Purchases")
        amount           = str(payload.get("amount", "0")).lstrip("-")
        narration        = payload.get("narration", "Purchase Return")
        vnum             = self._vch_id()
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="Debit Note" ACTION="Create">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
        <VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>Debit Note</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{purchase_ledger}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_contra_voucher(self, payload: dict) -> dict:
        """Cash/bank transfer between two cash or bank accounts."""
        date       = payload.get("date", "")
        from_acct  = payload.get("from_account", "Cash")
        to_acct    = payload.get("to_account", "Bank")
        amount     = str(payload.get("amount", "0")).lstrip("-")
        narration  = payload.get("narration", "Fund Transfer")
        vnum       = self._vch_id()
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="Contra" ACTION="Create">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
        <VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>Contra</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{to_acct}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{from_acct}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}
