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
        logger.debug("TALLY REQUEST:\n%s", xml_body)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self.base_url,
                    content=xml_body.encode("utf-8"),
                    headers={"Content-Type": "application/xml"},
                )
                resp.raise_for_status()
                logger.debug("TALLY RESPONSE:\n%s", resp.text)
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
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ProtocolError) as e:
            # TallyPrime crashed mid-request (e.g., c0000005 Access Violation).
            # This usually happens when deleting a master type with a known Tally bug
            # or when the record has dependencies. Treat as a Tally-side failure.
            raise TallyError(
                f"TallyPrime closed the connection unexpectedly (possible crash or unsupported operation). "
                f"Check TallyPrime is still running. Detail: {e}"
            )

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

    def _get_daybook_remoteid_map(self) -> dict:
        """Fetch the Day Book for TallyPrime's current active period and return a map
        of (vchnum, vchtype_lower) -> FinPilot REMOTEID for all FinPilot-created vouchers.

        Day Book is the only TallyPrime export that returns the actual REMOTEID stored on
        vouchers. The TDL Collection only returns the internal SENDERID/GUID as REMOTEID,
        which TallyPrime does not accept for deletion.

        FinPilot REMOTEID prefixes:
          FP-  accounting vouchers (Receipt, Payment, Sales, Purchase, Journal, Contra, etc.)
          SJ-  Stock Journal
          PS-  Physical Stock
          DN-  Delivery Note
          RN-  Receipt Note
          RI-  Rejections In
          RO-  Rejections Out
        """
        import re as _re
        _FP_PREFIXES = ("FP-", "SJ-", "PS-", "DN-", "RN-", "RI-", "RO-")
        xml = """<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>Day Book</ID></HEADER>
  <BODY><DESC><STATICVARIABLES>
    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
    <SVFROMDATE>20060101</SVFROMDATE>
    <SVTODATE>20991231</SVTODATE>
  </STATICVARIABLES></DESC></BODY>
</ENVELOPE>"""
        try:
            raw = self._post_xml(xml)
        except Exception:
            return {}
        remoteid_map: dict = {}
        for m in _re.finditer(r'(<VOUCHER[^>]+>)(.*?)(</VOUCHER>)', raw, _re.DOTALL):
            attrs = m.group(1)
            body  = m.group(2)
            rid_m   = _re.search(r'REMOTEID="([^"]+)"', attrs)
            vtype_m = _re.search(r'VCHTYPE="([^"]+)"', attrs)
            vnum_m  = _re.search(r'<VOUCHERNUMBER>(.*?)</VOUCHERNUMBER>', body)
            rid   = rid_m.group(1) if rid_m else ""
            vtype = (vtype_m.group(1) if vtype_m else "").lower().strip()
            vnum  = (vnum_m.group(1) if vnum_m else "").strip()
            if rid.startswith(_FP_PREFIXES) and vnum and vtype:
                remoteid_map[(vnum, vtype)] = rid
        return remoteid_map

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
            <FETCH>DATE,VOUCHERNUMBER,VOUCHERTYPENAME,NARRATION,PARTYLEDGERNAME,REMOTEID,ALLLEDGERENTRIES.LIST</FETCH>
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

        # Build Day Book map first — this is the only source of FP-xxx REMOTEIDs.
        # The Collection REMOTEID attribute returns TallyPrime's internal SENDERID/GUID
        # which cannot be used for delete. Day Book returns the actual FP-xxx.
        daybook_map = self._get_daybook_remoteid_map()

        vouchers = []
        for v in root.findall(".//VOUCHER"):
            date_el      = v.find("DATE")
            vchno_el     = v.find("VOUCHERNUMBER")
            vtype_el     = v.find("VOUCHERTYPENAME")
            narration_el = v.find("NARRATION")
            party_el     = v.find("PARTYLEDGERNAME")

            vnum  = vchno_el.text.strip()  if vchno_el  is not None and vchno_el.text  else ""
            vtype = vtype_el.text.strip()  if vtype_el  is not None and vtype_el.text  else ""

            # Prefer FP-xxx from Day Book (the real deletable REMOTEID).
            # Fall back to the Collection's REMOTEID attribute (internal SENDERID/GUID —
            # not usable for delete but kept so the backend can detect "synced from Tally").
            fp_remoteid = daybook_map.get((vnum, vtype.lower()), "")
            collection_guid = v.get("REMOTEID", "").strip()
            remoteid = fp_remoteid or collection_guid

            # Amount: try ledger list → any descendant AMOUNT → default 0
            amount_raw = "0"
            for path in (".//ALLLEDGERENTRIES.LIST/AMOUNT", ".//AMOUNT"):
                el = v.find(path)
                if el is not None and el.text and el.text.strip():
                    amount_raw = el.text.strip()
                    break

            vouchers.append({
                "date":           date_el.text.strip()      if date_el      is not None and date_el.text      else "",
                "voucher_number": vnum,
                "voucher_type":   vtype,
                "party":          party_el.text.strip()     if party_el     is not None and party_el.text     else "",
                "amount":         amount_raw.lstrip("-"),
                "narration":      narration_el.text.strip() if narration_el is not None and narration_el.text else "",
                "voucher_ref":    remoteid,
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
        """Fetch all stock items including their parent stock group (PARENT field)."""
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP StockItems</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP StockItems" ISMODIFY="No">
            <TYPE>StockItem</TYPE>
            <FETCH>NAME,PARENT,BASEUNITS,CLOSINGBALANCE,CLOSINGRATE</FETCH>
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
        items = []
        for item in root.findall(".//STOCKITEM"):
            # NAME is an XML attribute in TDL FETCH collections (same as GODOWN, STOCKGROUP, etc.)
            name      = (item.get("NAME") or "").strip()
            parent_el = item.find("PARENT")
            unit_el   = item.find("BASEUNITS")
            qty_el    = item.find("CLOSINGBALANCE")
            rate_el   = item.find("CLOSINGRATE")

            group = (parent_el.text or "").strip() if parent_el is not None else ""
            unit  = (unit_el.text or "").strip()   if unit_el   is not None else ""
            qty   = (qty_el.text or "0").strip()   if qty_el    is not None else "0"
            rate  = (rate_el.text or "0").strip()  if rate_el   is not None else "0"

            if not name:
                continue

            items.append({
                "name":            name,
                "stock_group":     group if group and group.lower() not in ("", "primary") else None,
                "unit":            unit,
                "closing_balance": qty,
                "closing_rate":    rate,
            })
        return items

    @staticmethod
    def _vch_id() -> str:
        """Generate a unique voucher remote ID."""
        return f"FP-{int(time.time() * 1000) % 100000000:08d}"

    @staticmethod
    def _fy_dates(date_yyyymmdd: str) -> tuple:
        """Return (fy_start, fy_end) in YYYYMMDD for the Indian FY containing the given date."""
        year = int(date_yyyymmdd[:4])
        month = int(date_yyyymmdd[4:6])
        if month >= 4:
            return f"{year}0401", f"{year + 1}0331"
        return f"{year - 1}0401", f"{year}0331"

    @staticmethod
    def _month_start(date_yyyymmdd: str) -> str:
        """Return the 1st of the month for the given YYYYMMDD.

        TallyPrime's GST split requires DATE == period SVFROMDATE (always the
        1st of the month). Mid-month dates fail with 'Voucher date is missing'.
        Normalising to month-start puts the entry in the correct GST period.
        """
        return date_yyyymmdd[:6] + "01"

    @staticmethod
    def _require_date(payload: dict, voucher_type: str) -> str:
        """
        Extract and validate the date from payload.
        Must be YYYYMMDD (8 digits). Raises TallyError with a clear message
        instead of sending <DATE></DATE> to TallyPrime and getting a confusing
        'Voucher date is missing' error from Tally.
        """
        date = str(payload.get("date", "")).strip()
        if not date:
            raise TallyError(
                f"{voucher_type} voucher: date is required. "
                "Please specify a date like '1 September 2026' or '2026-09-01'."
            )
        # Accept YYYYMMDD (8 digits) — the expected format from the backend
        if len(date) == 8 and date.isdigit():
            return date
        # Accept YYYY-MM-DD and strip dashes
        if len(date) == 10 and date[4] == '-' and date[7] == '-':
            return date.replace("-", "")
        raise TallyError(
            f"{voucher_type} voucher: invalid date format '{date}'. "
            "Expected YYYYMMDD (e.g. 20260901)."
        )

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

    # ── Read: Voucher Types ───────────────────────────────────────────────────

    def get_voucher_types(self) -> list[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP VoucherTypes</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP VoucherTypes" ISMODIFY="No">
            <TYPE>VoucherType</TYPE>
            <FETCH>NAME,PARENT,NUMBERINGMETHOD,ISACTIVE</FETCH>
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
            types = []
            for item in root.findall(".//VOUCHERTYPE"):
                name = (item.get("NAME") or "").strip()
                parent_el = item.find("PARENT")
                parent = parent_el.text.strip() if parent_el is not None and parent_el.text else ""
                active_el = item.find("ISACTIVE")
                is_active = (active_el.text or "").strip().lower() != "no" if active_el is not None else True
                nm_el = item.find("NUMBERINGMETHOD")
                numbering = nm_el.text.strip() if nm_el is not None and nm_el.text else "Automatic"
                if name:
                    types.append({
                        "name": name,
                        "parent": parent or None,
                        "numbering_method": numbering,
                        "is_active": is_active,
                    })
            return types
        except TallyError as e:
            logger.warning("get_voucher_types: %s", e)
            return []

    # ── Write: Create Voucher Type ────────────────────────────────────────────

    def create_voucher_type(self, payload: dict) -> dict:
        name = payload.get("name", "")
        parent = payload.get("parent", "Sales")
        numbering = payload.get("numbering_method", "Automatic")
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHERTYPE NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        <PARENT>{parent}</PARENT>
        <NUMBERINGMETHOD>{numbering}</NUMBERINGMETHOD>
        <ISACTIVE>Yes</ISACTIVE>
      </VOUCHERTYPE>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    # ── Read: Account Groups ─────────────────────────────────────────────────

    def get_groups(self) -> list[dict]:
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP Groups</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP Groups" ISMODIFY="No">
            <TYPE>Group</TYPE>
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
            for item in root.findall(".//GROUP"):
                name = (item.get("NAME") or "").strip()
                parent_el = item.find("PARENT")
                parent = parent_el.text.strip() if parent_el is not None and parent_el.text else ""
                if name and name.lower() != "primary":
                    groups.append({
                        "name": name,
                        "parent": parent if parent and parent.lower() != "primary" else None,
                    })
            return groups
        except TallyError as e:
            logger.warning("get_groups: %s", e)
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

    # ── Read: Stock Categories ────────────────────────────────────────────────

    def get_stock_categories(self) -> list[dict]:
        """Fetch all stock categories from TallyPrime (master data)."""
        xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>FP StockCategories</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP StockCategories" ISMODIFY="No">
            <TYPE>StockCategory</TYPE>
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
            cats = []
            for item in root.findall(".//STOCKCATEGORY"):
                name = (item.get("NAME") or "").strip()
                parent_el = item.find("PARENT")
                parent = parent_el.text.strip() if parent_el is not None and parent_el.text else ""
                if name and name.lower() not in ("primary", ""):
                    cats.append({"name": name, "parent": parent if parent and parent.lower() != "primary" else None})
            return cats
        except TallyError as e:
            logger.warning("get_stock_categories: %s", e)
            return []

    # ── Read: Stock Transactions (inventory vouchers) ─────────────────────────

    # Mapping from TallyPrime voucher type name → FinPilot transaction_type
    _STOCK_TXN_VTYPES = {
        "stock journal":   "STOCK_JOURNAL",
        "physical stock":  "PHYSICAL_STOCK",
        "delivery note":   "DELIVERY_NOTE",
        "receipt note":    "RECEIPT_NOTE",
        "rejections in":   "REJECTION_IN",
        "rejections out":  "REJECTION_OUT",
    }

    @staticmethod
    def _parse_qty(qty_str: str) -> tuple[float, str]:
        """Parse TallyPrime qty string like '5 Nos' or '-5 Nos' → (5.0, 'Nos')."""
        if not qty_str:
            return 0.0, ""
        parts = qty_str.strip().lstrip("-").split(None, 1)
        try:
            qty = abs(float(parts[0].replace(",", "")))
        except (ValueError, IndexError):
            qty = 0.0
        unit = parts[1].strip() if len(parts) > 1 else ""
        return qty, unit

    def get_stock_transactions(self, from_date: str = "", to_date: str = "") -> list[dict]:
        """
        Fetch inventory vouchers from TallyPrime:
        Stock Journal, Physical Stock, Delivery Note, Receipt Note,
        Rejections In, Rejections Out.

        These vouchers have ALLINVENTORYENTRIES.LIST (item movements)
        rather than ALLLEDGERENTRIES.LIST (monetary entries).
        """
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
    <ID>FP Stock Txns</ID>
  </HEADER>
  <BODY>
    <DESC>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="FP Stock Txns" ISMODIFY="No">
            <TYPE>Voucher</TYPE>
            <BELONGSTO>Yes</BELONGSTO>
            <FETCH>DATE,VOUCHERNUMBER,VOUCHERTYPENAME,NARRATION,PARTYLEDGERNAME,ALLINVENTORYENTRIES.LIST</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>{date_vars}
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            raw = self._post_xml(xml)
            root = self._parse_response(raw)

            # Day Book is the only source of SJ-/PS-/DN-/RN-/RI-/RO- REMOTEIDs.
            # The TDL Collection returns TallyPrime's internal SENDERID/GUID which
            # cannot be used for deletion. We match by (vch_no, vchtype_lower) and
            # replace the sequential VOUCHERNUMBER with the deletable REMOTEID.
            daybook_map = self._get_daybook_remoteid_map()

            txns = []

            for v in root.findall(".//VOUCHER"):
                vtype_el = v.find("VOUCHERTYPENAME")
                vtype_raw = (vtype_el.text or "").strip() if vtype_el is not None else ""
                txn_type = self._STOCK_TXN_VTYPES.get(vtype_raw.lower())
                if not txn_type:
                    continue  # skip accounting vouchers (Sales, Purchase, etc.)

                date_el   = v.find("DATE")
                vchno_el  = v.find("VOUCHERNUMBER")
                narr_el   = v.find("NARRATION")
                party_el  = v.find("PARTYLEDGERNAME")

                date_str  = (date_el.text or "").strip()  if date_el  is not None else ""
                vch_no    = (vchno_el.text or "").strip() if vchno_el is not None else ""
                narration = (narr_el.text or "").strip()  if narr_el  is not None else ""
                party     = (party_el.text or "").strip() if party_el is not None else ""

                # Prefer the actual FinPilot REMOTEID (SJ-/PS-/etc.) from Day Book
                # over the sequential VOUCHERNUMBER TallyPrime assigns ("7", "8"…).
                # The REMOTEID is what must be sent back to TallyPrime for deletion.
                fp_remoteid = daybook_map.get((vch_no, vtype_raw.lower()), "")
                if fp_remoteid:
                    vch_no = fp_remoteid

                entries = []
                from_godown = ""
                to_godown   = ""

                for inv in v.findall(".//ALLINVENTORYENTRIES.LIST"):
                    item_el = inv.find("STOCKITEMNAME")
                    item_name = (item_el.text or "").strip() if item_el is not None else ""
                    if not item_name:
                        continue

                    deemed_el = inv.find("ISDEEMEDPOSITIVE")
                    inward = (deemed_el.text or "").strip().lower() == "yes" if deemed_el is not None else True

                    # Get godown from BATCHALLOCATIONS.LIST if present, else from GODOWN
                    godown = ""
                    batch = inv.find(".//BATCHALLOCATIONS.LIST")
                    if batch is not None:
                        gd_el = batch.find("GODOWN")
                        godown = (gd_el.text or "").strip() if gd_el is not None else ""

                    qty_el  = inv.find("ACTUALQTY")
                    qty_raw = (qty_el.text or "").strip() if qty_el is not None else ""
                    qty, unit = self._parse_qty(qty_raw)

                    entries.append({
                        "stock_item_name": item_name,
                        "quantity": qty,
                        "unit": unit,
                        "rate": 0,
                        "godown": godown,
                        "inward": inward,
                    })

                    if inward and not to_godown:
                        to_godown = godown
                    elif not inward and not from_godown:
                        from_godown = godown

                if not entries:
                    continue  # skip vouchers with no inventory entries

                txns.append({
                    "transaction_type": txn_type,
                    "transaction_number": vch_no,
                    "date": date_str,
                    "narration": narration,
                    "party": party,
                    "from_godown": from_godown,
                    "to_godown": to_godown,
                    "voucher_type_name": vtype_raw,
                    "entries": entries,
                })

            return txns
        except TallyError as e:
            logger.warning("get_stock_transactions: %s", e)
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
        # Use explicit <NAME> child element — more stable across TallyPrime versions
        # than the empty-tag format which triggers c0000005 crashes in some builds.
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
        <{tag} NAME="{name}" ACTION="Delete">
          <NAME>{name}</NAME>
        </{tag}>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
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

    def delete_voucher_type(self, payload: dict) -> dict:
        return self._delete_master("VOUCHERTYPE", payload.get("name", ""))

    def delete_stock_item(self, payload: dict) -> dict:
        return self._delete_master("STOCKITEM", payload.get("name", ""))

    def delete_stock_category(self, payload: dict) -> dict:
        return self._delete_master("STOCKCATEGORY", payload.get("name", ""))

    # ── Write: Delete voucher permanently from TallyPrime ────────────────────

    def delete_voucher(self, payload: dict) -> dict:
        """
        Permanently delete a voucher from TallyPrime using ACTION="Delete".

        payload:
          voucher_ref:    REMOTEID (FP-xxxx) for FinPilot-created vouchers
          voucher_number: TallyPrime voucher number for Tally-native vouchers
          voucher_type:   TallyPrime voucher type name ("Sales" | "Purchase" | etc.)
          date:           Original voucher date YYYYMMDD (required to avoid date 0-0-0 error)

        ACTION="Delete" completely removes the voucher from TallyPrime (no strikethrough,
        no audit trail entry — the voucher is gone). Use ACTION="Cancel" only when you want
        to preserve the number in sequence with a cancellation mark.
        """
        vref         = payload.get("voucher_ref", "").strip()
        vnum         = payload.get("voucher_number", "").strip()
        voucher_type = payload.get("voucher_type", "Sales")

        if not vref and not vnum:
            raise TallyError("delete_voucher: voucher_ref (REMOTEID) or voucher_number is required")

        # DATE is required even for Delete — omitting causes "date 0-0-0 is Out of Range"
        from datetime import date as _date
        raw_date = str(payload.get("date", "")).strip()
        if raw_date and len(raw_date) == 8 and raw_date.isdigit():
            del_date = raw_date
        else:
            del_date = _date.today().strftime("%Y%m%d")
        del_date = del_date[:6] + "01"

        # TallyPrime needs fiscal year context to locate the voucher.
        # Without SVFROMDATE/SVTODATE it only searches the current active sub-period
        # and returns "Cannot delete unnamed object: VOUCHER!" for vouchers outside it.
        fy_start, fy_end = self._fy_dates(del_date)

        if vref:
            # FinPilot-created voucher: identify by REMOTEID attribute
            id_xml = f'REMOTEID="{vref}"'
            vnum_elem = ""
        else:
            # Tally-native voucher: VOUCHERNUMBER must be a child element (not attribute)
            # Using it as an attribute causes "unnamed object" error in TallyPrime
            id_xml = ""
            vnum_elem = f"<VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>"

        voucher_open = f'<VOUCHER {id_xml} VCHTYPE="{voucher_type}" ACTION="Delete">'.replace(
            '  VCHTYPE', ' VCHTYPE'  # normalise spacing when id_xml is empty
        ).strip()

        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      {voucher_open}
        {vnum_elem}
        <DATE>{del_date}</DATE>
        <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>
      </VOUCHER>
    </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        deleted  = root.find(".//DELETED")
        altered  = root.find(".//ALTERED")
        errors   = root.find(".//LINEERROR")
        if errors is not None and errors.text:
            raise TallyError(f"TallyPrime refused delete: {errors.text.strip()}")
        deleted_count = int(deleted.text) if deleted is not None and deleted.text else 0
        altered_count = int(altered.text) if altered is not None and altered.text else 0
        if deleted_count == 0 and altered_count == 0:
            raise TallyError(
                f"TallyPrime did not delete the voucher "
                f"(ref={vref or vnum!r}, type={voucher_type!r}). "
                "It may not exist or the identifier is wrong."
            )
        return {
            "deleted": deleted_count,
            "altered": altered_count,
            "voucher_ref": vref,
            "voucher_number": vnum,
        }

    # ── Write: Create sales voucher ───────────────────────────────────────────

    def create_sales_voucher(self, payload: dict) -> dict:
        """payload: date (YYYYMMDD), party_ledger, sales_ledger, amount, narration, voucher_type_name (optional custom type)"""
        vtype         = payload.get("voucher_type_name", "Sales")
        date          = self._require_date(payload, vtype)
        party         = payload.get("party_ledger", "")
        sales_ledger  = payload.get("sales_ledger", "Sales")
        amount        = str(payload.get("amount", "0")).lstrip("-")
        narration     = payload.get("narration", "")
        vnum          = payload.get("voucher_number") or self._vch_id()
        action        = "Alter" if payload.get("is_update") else "Create"
        fy_start, fy_end = self._fy_dates(date)

        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="{vtype}" ACTION="{action}" OBJVIEW="Accounting Voucher View">
        <DATE>{date}</DATE>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
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
    </TALLYMESSAGE></DATA>
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
        """payload: date (YYYYMMDD), party_ledger, purchase_ledger, amount, narration, voucher_type_name (optional custom type)"""
        vtype            = payload.get("voucher_type_name", "Purchase")
        date             = self._require_date(payload, vtype)
        party            = payload.get("party_ledger", "")
        purchase_ledger  = payload.get("purchase_ledger", "Purchases")
        amount           = str(payload.get("amount", "0")).lstrip("-")
        narration        = payload.get("narration", "")
        vnum             = payload.get("voucher_number") or self._vch_id()
        action           = "Alter" if payload.get("is_update") else "Create"
        fy_start, fy_end = self._fy_dates(date)

        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="{vtype}" ACTION="{action}" OBJVIEW="Accounting Voucher View">
        <DATE>{date}</DATE>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
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
    </TALLYMESSAGE></DATA>
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

    # ── Write: Create stock item ──────────────────────────────────────────────

    def create_stock_item(self, payload: dict) -> dict:
        name  = payload.get("name", "")
        unit  = (payload.get("unit") or "").strip()
        group = (payload.get("stock_group") or "").strip()
        rate  = float(payload.get("rate", 0) or 0)
        qty   = float(payload.get("opening_qty", 0) or 0)

        parent_xml = f"<PARENT>{group}</PARENT>" if group and group.lower() not in ("", "primary") else ""
        unit_xml   = f"<BASEUNITS>{unit}</BASEUNITS>" if unit else ""

        # Opening balance: only include if qty > 0 AND unit is set
        opening_xml = ""
        if qty > 0 and unit:
            value = round(qty * rate, 2)
            opening_xml = (
                f"<OPENINGBALANCE>{qty} {unit}</OPENINGBALANCE>"
                f"<OPENINGRATE>{rate}/{unit}</OPENINGRATE>"
                f"<OPENINGVALUE>{value}</OPENINGVALUE>"
            )

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
        <STOCKITEM NAME="{name}" ACTION="{"Alter" if payload.get("is_update") else "Create"}">
          <NAME>{name}</NAME>
          {parent_xml}
          {unit_xml}
          {opening_xml}
        </STOCKITEM>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_stock_category(self, payload: dict) -> dict:
        name = payload.get("name", "")
        raw_parent = (payload.get("parent") or "").strip()
        use_parent = raw_parent and raw_parent.lower() != "primary"
        parent_xml = f"<PARENT>{raw_parent}</PARENT>" if use_parent else ""
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <STOCKCATEGORY NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        {parent_xml}
      </STOCKCATEGORY>
    </TALLYMESSAGE>
  </DATA></BODY>
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
        # "Primary" is TallyPrime's implicit root — it cannot be referenced by name
        # in all editions (fails in EDU and some Silver builds). Omit the <PARENT>
        # tag entirely for root-level groups so Tally places them at the top level.
        raw_parent = (payload.get("parent") or "").strip()
        use_parent = raw_parent and raw_parent.lower() != "primary"
        parent_xml = f"<PARENT>{raw_parent}</PARENT>" if use_parent else ""
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <STOCKGROUP NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        {parent_xml}
      </STOCKGROUP>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_unit(self, payload: dict) -> dict:
        # NAME = formal/display name shown in unit list (e.g. "Numbers", "Kilograms")
        # ORIGINALNAME = short symbol/abbreviation (e.g. "Nos", "Kg")
        # ISSIMPLEUNIT=Yes is required — omitting it causes "BAD UNIT NAME" rejection.
        name     = payload.get("name", "").strip()
        symbol   = (payload.get("symbol") or name).strip()
        decimals = payload.get("decimal_places", "0")
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <UNIT NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        <ORIGINALNAME>{symbol}</ORIGINALNAME>
        <ISSIMPLEUNIT>Yes</ISSIMPLEUNIT>
        <DECIMALPLACES>{decimals}</DECIMALPLACES>
      </UNIT>
    </TALLYMESSAGE>
  </DATA></BODY>
</ENVELOPE>"""
        raw = self._post_xml(xml)
        root = self._parse_response(raw)
        created = root.find(".//CREATED")
        return {"created": int(created.text) if created is not None and created.text else 0}

    def create_godown(self, payload: dict) -> dict:
        name = payload.get("name", "")
        # Only include <PARENT> if a real named parent is given.
        # "Main Location" is the default root godown in some Tally builds but is
        # not guaranteed to exist (especially in EDU). Omit it for root godowns.
        raw_parent = (payload.get("parent") or "").strip()
        _skip = {"", "main location", "primary"}
        parent_xml = f"<PARENT>{raw_parent}</PARENT>" if raw_parent.lower() not in _skip else ""
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER>
  <BODY><DESC/><DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <GODOWN NAME="{name}" ACTION="Create">
        <NAME>{name}</NAME>
        {parent_xml}
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
        vtype     = payload.get("voucher_type_name", "Receipt")
        date      = self._require_date(payload, vtype)
        party     = payload.get("party_ledger", "")
        account   = payload.get("account_ledger", "Cash")
        amount    = str(payload.get("amount", "0")).lstrip("-")
        narration = payload.get("narration", "Receipt")
        vnum      = payload.get("voucher_number") or self._vch_id()
        action    = "Alter" if payload.get("is_update") else "Create"
        fy_start, fy_end = self._fy_dates(date)
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="{vtype}" ACTION="{action}" OBJVIEW="Accounting Voucher View">
        <DATE>{date}</DATE>
        <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{account}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>No</ISPARTYLEDGER>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
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
        vtype     = payload.get("voucher_type_name", "Payment")
        date      = self._require_date(payload, vtype)
        party     = payload.get("party_ledger", "")
        account   = payload.get("account_ledger", "Cash")
        amount    = str(payload.get("amount", "0")).lstrip("-")
        narration = payload.get("narration", "Payment")
        vnum      = payload.get("voucher_number") or self._vch_id()
        action    = "Alter" if payload.get("is_update") else "Create"
        fy_start, fy_end = self._fy_dates(date)
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="{vtype}" ACTION="{action}" OBJVIEW="Accounting Voucher View">
        <DATE>{date}</DATE>
        <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
          <AMOUNT>{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{account}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>No</ISPARTYLEDGER>
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
        vtype     = payload.get("voucher_type_name", "Journal")
        date      = self._require_date(payload, vtype)
        dr_ledger = payload.get("dr_ledger", "")
        cr_ledger = payload.get("cr_ledger", "")
        amount    = str(payload.get("amount", "0")).lstrip("-")
        narration = payload.get("narration", "Journal Entry")
        vnum      = payload.get("voucher_number") or self._vch_id()
        action    = "Alter" if payload.get("is_update") else "Create"
        fy_start, fy_end = self._fy_dates(date)
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="{vtype}" ACTION="{action}" OBJVIEW="Accounting Voucher View">
        <DATE>{date}</DATE>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{dr_ledger}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>No</ISPARTYLEDGER>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{cr_ledger}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>No</ISPARTYLEDGER>
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
        vtype         = payload.get("voucher_type_name", "Credit Note")
        date          = self._require_date(payload, vtype)
        party         = payload.get("party_ledger", "")
        sales_ledger  = payload.get("sales_ledger", "Sales")
        amount        = str(payload.get("amount", "0")).lstrip("-")
        narration     = payload.get("narration", "Sales Return")
        vnum          = payload.get("voucher_number") or self._vch_id()
        action        = "Alter" if payload.get("is_update") else "Create"
        fy_start, fy_end = self._fy_dates(date)
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="{vtype}" ACTION="{action}" OBJVIEW="Accounting Voucher View">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
        <ISINVOICE>No</ISINVOICE>
        <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{sales_ledger}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>No</ISPARTYLEDGER>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
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
        vtype            = payload.get("voucher_type_name", "Debit Note")
        date             = self._require_date(payload, vtype)
        party            = payload.get("party_ledger", "")
        purchase_ledger  = payload.get("purchase_ledger", "Purchases")
        amount           = str(payload.get("amount", "0")).lstrip("-")
        narration        = payload.get("narration", "Purchase Return")
        vnum             = payload.get("voucher_number") or self._vch_id()
        action           = "Alter" if payload.get("is_update") else "Create"
        fy_start, fy_end = self._fy_dates(date)
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="{vtype}" ACTION="{action}" OBJVIEW="Accounting Voucher View">
        <DATE>{date}</DATE>
        <EFFECTIVEDATE>{date}</EFFECTIVEDATE>
        <ISINVOICE>No</ISINVOICE>
        <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{party}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{purchase_ledger}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>No</ISPARTYLEDGER>
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

    # ── Write: Stock transaction vouchers ────────────────────────────────────

    def _build_inv_entry(
        self,
        item: str, qty: float, unit: str, rate: float,
        godown: str, is_deemed_positive: bool,
    ) -> str:
        """Build a single ALLINVENTORYENTRIES.LIST XML block."""
        amount = round(qty * rate, 2)
        # TallyPrime convention: goods IN (positive=Yes) → AMOUNT negative; goods OUT → positive
        amount_str = f"-{amount}" if is_deemed_positive else str(amount)
        deemed = "Yes" if is_deemed_positive else "No"
        return (
            f"        <ALLINVENTORYENTRIES.LIST>\n"
            f"          <STOCKITEMNAME>{item}</STOCKITEMNAME>\n"
            f"          <ISDEEMEDPOSITIVE>{deemed}</ISDEEMEDPOSITIVE>\n"
            f"          <GODOWNNAME>{godown}</GODOWNNAME>\n"
            f"          <RATE>{rate}/{unit}</RATE>\n"
            f"          <AMOUNT>{amount_str}</AMOUNT>\n"
            f"          <ACTUALQTY>{qty} {unit}</ACTUALQTY>\n"
            f"          <BILLEDQTY>{qty} {unit}</BILLEDQTY>\n"
            f"        </ALLINVENTORYENTRIES.LIST>"
        )

    def _inv_voucher_result(self, raw: str) -> dict:
        root = self._parse_response(raw)
        created    = root.find(".//CREATED")
        altered    = root.find(".//ALTERED")
        exceptions = root.find(".//EXCEPTIONS")
        lineerror  = root.find(".//LINEERROR")
        cr = int(created.text)    if created    is not None and created.text    else 0
        al = int(altered.text)    if altered    is not None and altered.text    else 0
        ex = int(exceptions.text) if exceptions is not None and exceptions.text else 0
        if lineerror is not None and lineerror.text:
            raise TallyError(f"TallyPrime error: {lineerror.text.strip()}")
        if cr == 0 and al == 0 and ex > 0:
            raise TallyError(
                "TallyPrime: inventory voucher not created (exception). "
                "Check that: (1) the godown name exists in TallyPrime, "
                "(2) the stock item name is exact, "
                "(3) the unit matches the item's unit in TallyPrime, "
                "(4) the voucher type is active and godown tracking is enabled."
            )
        return {"created": cr, "altered": al}

    def create_stock_journal(self, payload: dict) -> dict:
        """Transfer stock between godowns (Stock Journal voucher).

        TallyPrime Stock Journal uses INVENTORYENTRIESOUT.LIST for the source
        godown and INVENTORYENTRIESIN.LIST for the destination godown — NOT the
        ALLINVENTORYENTRIES.LIST tag used by other inventory voucher types.
        """
        date        = self._require_date(payload, "Stock Journal")
        txn_number  = payload.get("transaction_number") or self._vch_id()
        narration   = payload.get("narration", "")
        from_godown = (payload.get("from_godown") or "").strip() or "Main Location"
        to_godown   = (payload.get("to_godown") or "").strip() or "Main Location"
        entries     = [e for e in (payload.get("entries") or []) if e.get("stock_item_name")]
        if not entries:
            raise TallyError(
                "Stock Journal: at least one stock item entry is required. "
                "Add the stock item name and quantity before creating."
            )
        fy_start, fy_end = self._fy_dates(date)

        out_blocks = []  # source — goods leaving
        in_blocks  = []  # destination — goods arriving
        for e in entries:
            item   = e.get("stock_item_name", "")
            qty    = float(e.get("quantity") or 0)
            unit   = (e.get("unit") or "Nos").strip()
            rate   = float(e.get("rate") or 0)
            gd     = (e.get("godown") or "").strip()
            src_gd = gd or from_godown
            amount = round(qty * rate, 2)

            out_blocks.append(
                f"        <INVENTORYENTRIESOUT.LIST>\n"
                f"          <STOCKITEMNAME>{item}</STOCKITEMNAME>\n"
                f"          <GODOWNNAME>{src_gd}</GODOWNNAME>\n"
                f"          <RATE>{rate}/{unit}</RATE>\n"
                f"          <AMOUNT>{amount}</AMOUNT>\n"
                f"          <ACTUALQTY>{qty} {unit}</ACTUALQTY>\n"
                f"          <BILLEDQTY>{qty} {unit}</BILLEDQTY>\n"
                f"        </INVENTORYENTRIESOUT.LIST>"
            )
            in_blocks.append(
                f"        <INVENTORYENTRIESIN.LIST>\n"
                f"          <STOCKITEMNAME>{item}</STOCKITEMNAME>\n"
                f"          <GODOWNNAME>{to_godown}</GODOWNNAME>\n"
                f"          <RATE>{rate}/{unit}</RATE>\n"
                f"          <AMOUNT>-{amount}</AMOUNT>\n"
                f"          <ACTUALQTY>{qty} {unit}</ACTUALQTY>\n"
                f"          <BILLEDQTY>{qty} {unit}</BILLEDQTY>\n"
                f"        </INVENTORYENTRIESIN.LIST>"
            )

        entries_xml = "\n".join(out_blocks + in_blocks)
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{txn_number}" VCHTYPE="Stock Journal" ACTION="{"Alter" if payload.get("is_update") else "Create"}" OBJVIEW="Inventory Voucher View">
        <DATE>{date}</DATE>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>Stock Journal</VOUCHERTYPENAME>
        <VOUCHERNUMBER>{txn_number}</VOUCHERNUMBER>
{entries_xml}
      </VOUCHER>
    </TALLYMESSAGE></DATA>
  </BODY>
</ENVELOPE>"""
        return self._inv_voucher_result(self._post_xml(xml))

    def create_physical_stock(self, payload: dict) -> dict:
        """Adjust stock to physical count (Physical Stock voucher)."""
        date       = self._require_date(payload, "Physical Stock")
        txn_number = payload.get("transaction_number") or self._vch_id()
        narration  = payload.get("narration", "")
        entries    = [e for e in (payload.get("entries") or []) if e.get("stock_item_name")]
        if not entries:
            raise TallyError(
                "Physical Stock: at least one stock item entry is required. "
                "Add the stock item name and quantity before creating."
            )
        fy_start, fy_end = self._fy_dates(date)

        entry_blocks = []
        for e in entries:
            item  = e.get("stock_item_name", "")
            qty   = float(e.get("quantity") or 0)
            unit  = (e.get("unit") or "Nos").strip()
            rate  = float(e.get("rate") or 0)
            godown = (e.get("godown") or (payload.get("from_godown") or "")).strip() or "Main Location"
            entry_blocks.append(self._build_inv_entry(item, qty, unit, rate, godown, True))

        entries_xml = "\n".join(entry_blocks)
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{txn_number}" VCHTYPE="Physical Stock" ACTION="{"Alter" if payload.get("is_update") else "Create"}" OBJVIEW="Inventory Voucher View">
        <DATE>{date}</DATE>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>Physical Stock</VOUCHERTYPENAME>
        <VOUCHERNUMBER>{txn_number}</VOUCHERNUMBER>
{entries_xml}
      </VOUCHER>
    </TALLYMESSAGE></DATA>
  </BODY>
</ENVELOPE>"""
        return self._inv_voucher_result(self._post_xml(xml))

    def _party_inv_voucher(
        self, vchtype: str, payload: dict, is_deemed_positive: bool
    ) -> dict:
        """Build a party-based inventory voucher (Delivery Note / Receipt Note / Rejection In/Out)."""
        date        = self._require_date(payload, vchtype)
        txn_number  = payload.get("transaction_number") or self._vch_id()
        narration   = payload.get("narration", "")
        party       = payload.get("party_name", "")
        entries     = [e for e in (payload.get("entries") or []) if e.get("stock_item_name")]
        if not entries:
            raise TallyError(
                f"{vchtype}: at least one stock item entry is required. "
                "Add the stock item name and quantity before creating."
            )
        from_godown = (payload.get("from_godown") or "").strip()
        fy_start, fy_end = self._fy_dates(date)

        entry_blocks = []
        for e in entries:
            item   = e.get("stock_item_name", "")
            qty    = float(e.get("quantity") or 0)
            unit   = (e.get("unit") or "Nos").strip()
            rate   = float(e.get("rate") or 0)
            godown = (e.get("godown") or from_godown or "").strip() or "Main Location"
            entry_blocks.append(self._build_inv_entry(item, qty, unit, rate, godown, is_deemed_positive))

        entries_xml = "\n".join(entry_blocks)
        party_xml = f"\n        <PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>" if party else ""
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{txn_number}" VCHTYPE="{vchtype}" ACTION="{"Alter" if payload.get("is_update") else "Create"}" OBJVIEW="Inventory Voucher View">
        <DATE>{date}</DATE>{party_xml}
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vchtype}</VOUCHERTYPENAME>
        <VOUCHERNUMBER>{txn_number}</VOUCHERNUMBER>
{entries_xml}
      </VOUCHER>
    </TALLYMESSAGE></DATA>
  </BODY>
</ENVELOPE>"""
        return self._inv_voucher_result(self._post_xml(xml))

    def create_delivery_note(self, payload: dict) -> dict:
        """Goods out to customer (Delivery Note, ISDEEMEDPOSITIVE=No → decreases stock)."""
        return self._party_inv_voucher("Delivery Note", payload, is_deemed_positive=False)

    def create_receipt_note(self, payload: dict) -> dict:
        """Goods in from supplier (Receipt Note, ISDEEMEDPOSITIVE=Yes → increases stock)."""
        return self._party_inv_voucher("Receipt Note", payload, is_deemed_positive=True)

    def create_rejection_in(self, payload: dict) -> dict:
        """Customer returns goods to you (Rejections In, ISDEEMEDPOSITIVE=Yes → increases stock)."""
        return self._party_inv_voucher("Rejections In", payload, is_deemed_positive=True)

    def create_rejection_out(self, payload: dict) -> dict:
        """You return goods to supplier (Rejections Out, ISDEEMEDPOSITIVE=No → decreases stock)."""
        return self._party_inv_voucher("Rejections Out", payload, is_deemed_positive=False)

    def create_contra_voucher(self, payload: dict) -> dict:
        """Cash/bank transfer between two cash or bank accounts."""
        vtype      = payload.get("voucher_type_name", "Contra")
        date       = self._require_date(payload, vtype)
        from_acct  = payload.get("from_account", "Cash")
        to_acct    = payload.get("to_account", "Bank")
        amount     = str(payload.get("amount", "0")).lstrip("-")
        narration  = payload.get("narration", "Fund Transfer")
        vnum       = payload.get("voucher_number") or self._vch_id()
        fy_start, fy_end = self._fy_dates(date)
        xml = f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>Vouchers</ID></HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVFROMDATE>{fy_start}</SVFROMDATE>
        <SVTODATE>{fy_end}</SVTODATE>
      </STATICVARIABLES>
    </DESC>
    <DATA>
    <TALLYMESSAGE xmlns:UDF="TallyUDF">
      <VOUCHER REMOTEID="{vnum}" VCHTYPE="{vtype}" ACTION="Create" OBJVIEW="Accounting Voucher View">
        <DATE>{date}</DATE>
        <NARRATION>{narration}</NARRATION>
        <VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{to_acct}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>No</ISPARTYLEDGER>
          <AMOUNT>-{amount}</AMOUNT>
        </ALLLEDGERENTRIES.LIST>
        <ALLLEDGERENTRIES.LIST>
          <LEDGERNAME>{from_acct}</LEDGERNAME>
          <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          <ISPARTYLEDGER>No</ISPARTYLEDGER>
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
