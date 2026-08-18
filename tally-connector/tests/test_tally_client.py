"""
Unit tests for TallyClient — no live TallyPrime required.
All HTTP calls are mocked via direct _post_xml monkey-patching or httpx.Client patch.

Key behaviours tested here (facts confirmed against live TallyPrime):

DELETE:
  • TallyPrime only deletes vouchers identified by REMOTEID attribute.
  • VOUCHERNUMBER as XML attribute causes "Cannot delete unnamed object: VOUCHER!".
  • VOUCHERNUMBER as child element also fails — only REMOTEID works for FinPilot-created.
  • SVFROMDATE/SVTODATE must be present so TallyPrime searches the full fiscal year.

REMOTEID ENRICHMENT (Day Book):
  • TDL Collection REMOTEID attribute = TallyPrime internal SENDERID/GUID, NOT deletable.
  • Day Book REMOTEID attribute = actual FinPilot REMOTEID (FP-/SJ-/PS-/etc.), deletable.
  • _get_daybook_remoteid_map() builds (vchnum, vchtype_lower) → REMOTEID from Day Book.
  • get_vouchers() and get_stock_transactions() both call _get_daybook_remoteid_map() to
    recover the deletable REMOTEID after a wipe+resync.

STOCK TRANSACTIONS:
  • TallyPrime overwrites <VOUCHERNUMBER> with a sequential number ("7", "8"…)
    even when FinPilot sets it explicitly to "SJ-xxx". The sequential number is
    NOT usable for deletion. The Day Book returns the original SJ-/PS-/etc. REMOTEID.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tally_client import TallyClient, TallyError


# ─── XML fixtures ─────────────────────────────────────────────────────────────

SAMPLE_COMPANY_XML = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<COMPANY><NAME>Test Company Ltd</NAME></COMPANY>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""

SAMPLE_LEDGER_XML = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<LEDGER NAME="Cash"><PARENT>Cash-in-Hand</PARENT><CLOSINGBALANCE>10000</CLOSINGBALANCE></LEDGER>
<LEDGER NAME="Bank OD Account"><PARENT>Bank OD A/c</PARENT><CLOSINGBALANCE>50000</CLOSINGBALANCE></LEDGER>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""

# Collection-format voucher XML (VOUCHERNUMBER is TallyPrime's sequential number)
SAMPLE_VOUCHER_XML = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<VOUCHER>
  <DATE>20260814</DATE>
  <VOUCHERNUMBER>42</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
  <NARRATION>Invoice 001</NARRATION>
  <PARTYLEDGERNAME>ABC Traders</PARTYLEDGERNAME>
  <AMOUNT>50000</AMOUNT>
</VOUCHER>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""

# Collection-format for a Receipt voucher whose REMOTEID we want to recover
SAMPLE_RECEIPT_COLLECTION_XML = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<VOUCHER>
  <DATE>20260901</DATE>
  <VOUCHERNUMBER>19</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
  <NARRATION>Payment from customer</NARRATION>
  <PARTYLEDGERNAME>Cash</PARTYLEDGERNAME>
</VOUCHER>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""

# Day Book-format: REMOTEID is an XML attribute on the VOUCHER tag
# (the only format that exposes the actual FP-xxx REMOTEID)
SAMPLE_DAYBOOK_WITH_FP_XML = """<ENVELOPE>
<BODY><DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
<VOUCHER REMOTEID="FP-BA84BC6F2ADE" VCHTYPE="Receipt" ACTION="Create">
  <DATE>20260901</DATE>
  <VOUCHERNUMBER>19</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
</VOUCHER>
</TALLYMESSAGE></DATA></BODY>
</ENVELOPE>"""

# Day Book with SJ- REMOTEID (Stock Journal)
SAMPLE_DAYBOOK_WITH_SJ_XML = """<ENVELOPE>
<BODY><DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
<VOUCHER REMOTEID="SJ-A8AC2842" VCHTYPE="Stock Journal" ACTION="Create">
  <DATE>20260902</DATE>
  <VOUCHERNUMBER>8</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Stock Journal</VOUCHERTYPENAME>
</VOUCHER>
</TALLYMESSAGE></DATA></BODY>
</ENVELOPE>"""

# Day Book with all FinPilot prefixes
SAMPLE_DAYBOOK_ALL_PREFIXES_XML = """<ENVELOPE>
<BODY><DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
<VOUCHER REMOTEID="FP-AABBCC001122" VCHTYPE="Receipt" ACTION="Create">
  <DATE>20260901</DATE><VOUCHERNUMBER>19</VOUCHERNUMBER>
</VOUCHER>
<VOUCHER REMOTEID="SJ-A8AC2842" VCHTYPE="Stock Journal" ACTION="Create">
  <DATE>20260902</DATE><VOUCHERNUMBER>8</VOUCHERNUMBER>
</VOUCHER>
<VOUCHER REMOTEID="PS-CCD0F9F0" VCHTYPE="Physical Stock" ACTION="Create">
  <DATE>20260902</DATE><VOUCHERNUMBER>13</VOUCHERNUMBER>
</VOUCHER>
<VOUCHER REMOTEID="DN-A7093113" VCHTYPE="Delivery Note" ACTION="Create">
  <DATE>20260902</DATE><VOUCHERNUMBER>8</VOUCHERNUMBER>
</VOUCHER>
<VOUCHER REMOTEID="RN-B308B5D8" VCHTYPE="Receipt Note" ACTION="Create">
  <DATE>20260902</DATE><VOUCHERNUMBER>8</VOUCHERNUMBER>
</VOUCHER>
<VOUCHER REMOTEID="RI-0E9CA2F4" VCHTYPE="Rejections In" ACTION="Create">
  <DATE>20260902</DATE><VOUCHERNUMBER>7</VOUCHERNUMBER>
</VOUCHER>
<VOUCHER REMOTEID="RO-C965CCBE" VCHTYPE="Rejections Out" ACTION="Create">
  <DATE>20260902</DATE><VOUCHERNUMBER>7</VOUCHERNUMBER>
</VOUCHER>
<VOUCHER REMOTEID="7c34fc3f-2609-438f-931c-79d6d51d19b8-000001d1" VCHTYPE="Purchase" ACTION="Create">
  <DATE>20260901</DATE><VOUCHERNUMBER>38</VOUCHERNUMBER>
</VOUCHER>
</TALLYMESSAGE></DATA></BODY>
</ENVELOPE>"""

# Collection XML for stock transactions (VOUCHERNUMBER is TallyPrime sequential)
SAMPLE_STOCK_TXN_COLLECTION_XML = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<VOUCHER>
  <DATE>20260902</DATE>
  <VOUCHERNUMBER>8</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Stock Journal</VOUCHERTYPENAME>
  <NARRATION>Godown transfer</NARRATION>
  <ALLINVENTORYENTRIES.LIST>
    <STOCKITEMNAME>Laptop</STOCKITEMNAME>
    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
    <ACTUALQTY>5 Nos</ACTUALQTY>
    <BATCHALLOCATIONS.LIST>
      <GODOWN>Main Warehouse</GODOWN>
    </BATCHALLOCATIONS.LIST>
  </ALLINVENTORYENTRIES.LIST>
</VOUCHER>
<VOUCHER>
  <DATE>20260902</DATE>
  <VOUCHERNUMBER>13</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Physical Stock</VOUCHERTYPENAME>
  <NARRATION>Stock count</NARRATION>
  <ALLINVENTORYENTRIES.LIST>
    <STOCKITEMNAME>Remote</STOCKITEMNAME>
    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
    <ACTUALQTY>110 Nos</ACTUALQTY>
    <BATCHALLOCATIONS.LIST>
      <GODOWN>Main Location</GODOWN>
    </BATCHALLOCATIONS.LIST>
  </ALLINVENTORYENTRIES.LIST>
</VOUCHER>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""

SAMPLE_STOCK_XML = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<STOCKITEM NAME="Widget A">
  <PARENT>Electronics</PARENT>
  <BASEUNITS>Nos</BASEUNITS>
  <CLOSINGBALANCE>100</CLOSINGBALANCE>
  <CLOSINGRATE>250</CLOSINGRATE>
</STOCKITEM>
<STOCKITEM NAME="Remote">
  <PARENT>Tablets</PARENT>
  <BASEUNITS>Nos</BASEUNITS>
  <CLOSINGBALANCE>50 Nos</CLOSINGBALANCE>
  <CLOSINGRATE>500 /Nos</CLOSINGRATE>
</STOCKITEM>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""

SAMPLE_WRITE_OK_XML = """<ENVELOPE>
<BODY><DATA>
<IMPORTRESULT><CREATED>1</CREATED><ALTERED>0</ALTERED><DELETED>0</DELETED></IMPORTRESULT>
</DATA></BODY>
</ENVELOPE>"""

SAMPLE_DELETE_OK_XML = """<ENVELOPE>
<BODY><DATA>
<IMPORTRESULT><CREATED>0</CREATED><ALTERED>0</ALTERED><DELETED>1</DELETED></IMPORTRESULT>
</DATA></BODY>
</ENVELOPE>"""

SAMPLE_DELETE_ZERO_XML = """<ENVELOPE>
<BODY><DATA>
<IMPORTRESULT><CREATED>0</CREATED><ALTERED>0</ALTERED><DELETED>0</DELETED></IMPORTRESULT>
</DATA></BODY>
</ENVELOPE>"""

SAMPLE_ERROR_XML = """<ENVELOPE>
<BODY><DATA>
<LINEERROR>Ledger not found</LINEERROR>
</DATA></BODY>
</ENVELOPE>"""

SAMPLE_NOT_FOUND_XML = """<ENVELOPE>
<BODY><DATA>
<LINEERROR>SJ-A8AC2842 does not exist</LINEERROR>
</DATA></BODY>
</ENVELOPE>"""

SAMPLE_DAYBOOK_EMPTY_XML = """<ENVELOPE>
<BODY><DATA></DATA></BODY>
</ENVELOPE>"""


def _mock_client(response_text: str, status_code: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.text = response_text
    mock_resp.status_code = status_code
    mock_resp.raise_for_status = MagicMock()

    mock_http = MagicMock()
    mock_http.__enter__ = MagicMock(return_value=mock_http)
    mock_http.__exit__ = MagicMock(return_value=False)
    mock_http.post = MagicMock(return_value=mock_resp)
    mock_http.get = MagicMock(return_value=mock_resp)
    return mock_http


# ─── Tests: basic connectivity ────────────────────────────────────────────────

class TestIsReachable:
    def test_returns_true_when_tally_responds(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client("")):
            assert client.is_reachable() is True

    def test_returns_false_on_connect_error(self):
        import httpx
        client = TallyClient()
        mock_http = _mock_client("")
        mock_http.get.side_effect = httpx.ConnectError("refused")
        with patch("httpx.Client", return_value=mock_http):
            assert client.is_reachable() is False


class TestGetActiveCompany:
    def test_parses_company_name(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_COMPANY_XML)):
            result = client.get_active_company()
        assert result is not None
        assert result["name"] == "Test Company Ltd"

    def test_returns_none_when_no_company_tag(self):
        xml = "<ENVELOPE><BODY><DATA><COLLECTION></COLLECTION></DATA></BODY></ENVELOPE>"
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(xml)):
            result = client.get_active_company()
        assert result is None

    def test_returns_none_on_tally_error(self):
        import httpx
        client = TallyClient()
        mock_http = _mock_client("")
        mock_http.post.side_effect = httpx.ConnectError("refused")
        with patch("httpx.Client", return_value=mock_http):
            result = client.get_active_company()
        assert result is None


# ─── Tests: ledgers ───────────────────────────────────────────────────────────

class TestGetLedgers:
    def test_parses_ledger_list(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_LEDGER_XML)):
            ledgers = client.get_ledgers()
        assert len(ledgers) == 2
        assert ledgers[0]["name"] == "Cash"
        assert ledgers[0]["group"] == "Cash-in-Hand"
        assert ledgers[0]["closing_balance"] == "10000"

    def test_raises_on_connect_error(self):
        import httpx
        client = TallyClient()
        mock_http = _mock_client("")
        mock_http.post.side_effect = httpx.ConnectError("refused")
        with patch("httpx.Client", return_value=mock_http):
            with pytest.raises(TallyError, match="Cannot connect"):
                client.get_ledgers()


# ─── Tests: Day Book REMOTEID map ─────────────────────────────────────────────

class TestDaybookRemoteidMap:
    """
    _get_daybook_remoteid_map() is the foundation of the REMOTEID-preservation fix.
    It extracts FinPilot-issued REMOTEIDs from the Day Book XML (where they appear
    as attributes on the VOUCHER element, unlike TDL Collection which returns GUIDs).
    """

    def test_captures_fp_prefix(self):
        client = TallyClient()
        client._post_xml = lambda _xml: SAMPLE_DAYBOOK_WITH_FP_XML
        result = client._get_daybook_remoteid_map()
        assert result[("19", "receipt")] == "FP-BA84BC6F2ADE"

    def test_captures_sj_prefix(self):
        client = TallyClient()
        client._post_xml = lambda _xml: SAMPLE_DAYBOOK_WITH_SJ_XML
        result = client._get_daybook_remoteid_map()
        assert result[("8", "stock journal")] == "SJ-A8AC2842"

    def test_captures_all_finpilot_prefixes(self):
        """All six FinPilot inventory prefixes must be captured."""
        client = TallyClient()
        client._post_xml = lambda _xml: SAMPLE_DAYBOOK_ALL_PREFIXES_XML
        result = client._get_daybook_remoteid_map()
        assert result[("19",  "receipt")]        == "FP-AABBCC001122"
        assert result[("8",   "stock journal")]  == "SJ-A8AC2842"
        assert result[("13",  "physical stock")] == "PS-CCD0F9F0"
        assert result[("8",   "delivery note")]  == "DN-A7093113"
        assert result[("8",   "receipt note")]   == "RN-B308B5D8"
        assert result[("7",   "rejections in")]  == "RI-0E9CA2F4"
        assert result[("7",   "rejections out")] == "RO-C965CCBE"

    def test_ignores_guid_format_remoteid(self):
        """TallyPrime internal GUIDs (7c34fc3f-...) must NOT be captured — they
        are TallyPrime's SENDERID, not deletable REMOTEIDs."""
        client = TallyClient()
        client._post_xml = lambda _xml: SAMPLE_DAYBOOK_ALL_PREFIXES_XML
        result = client._get_daybook_remoteid_map()
        # Purchase 38 has a GUID-format REMOTEID — must not appear
        assert ("38", "purchase") not in result

    def test_returns_empty_on_http_failure(self):
        import httpx
        client = TallyClient()
        def raise_error(_xml):
            raise httpx.ConnectError("refused")
        client._post_xml = raise_error
        result = client._get_daybook_remoteid_map()
        assert result == {}

    def test_returns_empty_when_no_finpilot_vouchers(self):
        client = TallyClient()
        client._post_xml = lambda _xml: SAMPLE_DAYBOOK_EMPTY_XML
        result = client._get_daybook_remoteid_map()
        assert result == {}

    def test_key_uses_lowercase_vchtype(self):
        """Keys must be lowercase so they match against Collection data case-insensitively."""
        client = TallyClient()
        client._post_xml = lambda _xml: SAMPLE_DAYBOOK_WITH_FP_XML
        result = client._get_daybook_remoteid_map()
        # Key must be lowercase, not "Receipt"
        assert ("19", "receipt") in result
        assert ("19", "Receipt") not in result


# ─── Tests: get_vouchers with Day Book enrichment ─────────────────────────────

class TestGetVouchers:
    """
    get_vouchers() makes two calls:
      1. TDL Collection (period-independent) — returns all vouchers with sequential VOUCHERNUMBER
      2. _get_daybook_remoteid_map() (Day Book) — returns FP-xxx REMOTEIDs

    The enrichment replaces the empty/GUID voucher_ref with the FP-xxx from Day Book.
    """

    def test_returns_voucher_ref_field(self):
        """Every returned voucher dict must include the 'voucher_ref' key."""
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_VOUCHER_XML)):
            vouchers = client.get_vouchers()
        assert "voucher_ref" in vouchers[0]

    def test_enriches_voucher_ref_from_daybook(self):
        """When Day Book has a FP-xxx for this voucher, voucher_ref must be set to it."""
        client = TallyClient()
        # Inject Day Book map directly — avoids httpx mock complexity
        client._get_daybook_remoteid_map = lambda: {("19", "receipt"): "FP-BA84BC6F2ADE"}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_RECEIPT_COLLECTION_XML)):
            vouchers = client.get_vouchers()
        assert len(vouchers) == 1
        assert vouchers[0]["voucher_ref"] == "FP-BA84BC6F2ADE"

    def test_voucher_ref_empty_when_no_daybook_match(self):
        """When Day Book has no match (Tally-native voucher), voucher_ref is empty or GUID."""
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_RECEIPT_COLLECTION_XML)):
            vouchers = client.get_vouchers()
        # No FP-xxx from Day Book, no REMOTEID attribute on Collection VOUCHER → empty
        assert vouchers[0]["voucher_ref"] == ""

    def test_existing_voucher_fields_still_populated(self):
        """Day Book enrichment must not break the other fields."""
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_VOUCHER_XML)):
            vouchers = client.get_vouchers()
        assert len(vouchers) == 1
        assert vouchers[0]["voucher_type"] == "Sales"
        assert vouchers[0]["party"] == "ABC Traders"

    def test_sales_filter(self):
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_VOUCHER_XML)):
            sales = client.get_sales()
        assert len(sales) == 1
        assert "Sales" in sales[0]["voucher_type"]

    def test_purchases_filter_returns_empty_when_none(self):
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_VOUCHER_XML)):
            purchases = client.get_purchases()
        assert len(purchases) == 0

    def test_fp_remoteid_preferred_over_collection_guid(self):
        """If Collection VOUCHER has a GUID-format REMOTEID attribute AND Day Book has FP-xxx,
        the FP-xxx wins (it's the deletable one)."""
        # Collection XML with a GUID in the VOUCHER attribute (what TallyPrime actually returns)
        collection_with_guid = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<VOUCHER REMOTEID="7c34fc3f-2609-438f-931c-79d6d51d19b8-000001d5">
  <DATE>20260901</DATE>
  <VOUCHERNUMBER>19</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
  <PARTYLEDGERNAME>Cash</PARTYLEDGERNAME>
</VOUCHER>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {("19", "receipt"): "FP-BA84BC6F2ADE"}
        with patch("httpx.Client", return_value=_mock_client(collection_with_guid)):
            vouchers = client.get_vouchers()
        assert vouchers[0]["voucher_ref"] == "FP-BA84BC6F2ADE"

    def test_collection_guid_used_as_fallback_when_no_daybook(self):
        """When Day Book has no match, fall back to Collection GUID so the field is not lost."""
        collection_with_guid = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<VOUCHER REMOTEID="7c34fc3f-2609-438f-931c-79d6d51d19b8-000001d5">
  <DATE>20260901</DATE>
  <VOUCHERNUMBER>20</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
  <PARTYLEDGERNAME>Cash</PARTYLEDGERNAME>
</VOUCHER>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}  # No Day Book match
        with patch("httpx.Client", return_value=_mock_client(collection_with_guid)):
            vouchers = client.get_vouchers()
        assert vouchers[0]["voucher_ref"] == "7c34fc3f-2609-438f-931c-79d6d51d19b8-000001d5"


# ─── Tests: get_stock_transactions with Day Book enrichment ───────────────────

class TestGetStockTransactions:
    """
    get_stock_transactions() has the same Day Book enrichment as get_vouchers().

    Critical: TallyPrime overwrites <VOUCHERNUMBER>SJ-xxx</VOUCHERNUMBER> with a
    sequential number ("8"). The Day Book is the only source of the original SJ-/PS-/etc.
    REMOTEID that is needed for deletion.
    """

    def test_enriches_sj_transaction_number_from_daybook(self):
        """After wipe+resync, transaction_number must be SJ-xxx (deletable) not '8'."""
        client = TallyClient()
        # Day Book knows sequential "8" → "SJ-A8AC2842"
        client._get_daybook_remoteid_map = lambda: {("8", "stock journal"): "SJ-A8AC2842"}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_STOCK_TXN_COLLECTION_XML)):
            txns = client.get_stock_transactions()
        sj = next(t for t in txns if t["transaction_type"] == "STOCK_JOURNAL")
        assert sj["transaction_number"] == "SJ-A8AC2842", \
            "Sequential VOUCHERNUMBER '8' must be replaced with SJ-xxx for deletion to work"

    def test_enriches_ps_transaction_number_from_daybook(self):
        """Physical Stock transaction_number must be PS-xxx after enrichment."""
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {
            ("8",  "stock journal"): "SJ-A8AC2842",
            ("13", "physical stock"): "PS-CCD0F9F0",
        }
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_STOCK_TXN_COLLECTION_XML)):
            txns = client.get_stock_transactions()
        ps = next(t for t in txns if t["transaction_type"] == "PHYSICAL_STOCK")
        assert ps["transaction_number"] == "PS-CCD0F9F0"

    def test_uses_sequential_number_when_no_daybook_match(self):
        """When Day Book has no match (Tally-native stock txn), keep sequential VOUCHERNUMBER."""
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}  # No Day Book data
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_STOCK_TXN_COLLECTION_XML)):
            txns = client.get_stock_transactions()
        assert txns[0]["transaction_number"] == "8"   # Sequential fallback

    def test_parses_stock_journal_entries(self):
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_STOCK_TXN_COLLECTION_XML)):
            txns = client.get_stock_transactions()
        sj = next(t for t in txns if t["transaction_type"] == "STOCK_JOURNAL")
        assert len(sj["entries"]) == 1
        assert sj["entries"][0]["stock_item_name"] == "Laptop"
        assert sj["entries"][0]["quantity"] == 5.0

    def test_parses_godown_from_batch_allocations(self):
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_STOCK_TXN_COLLECTION_XML)):
            txns = client.get_stock_transactions()
        sj = next(t for t in txns if t["transaction_type"] == "STOCK_JOURNAL")
        assert sj["to_godown"] == "Main Warehouse"

    def test_skips_vouchers_with_no_inventory_entries(self):
        """Accounting vouchers (Sales, Purchase) have no ALLINVENTORYENTRIES.LIST — skip them."""
        xml = """<ENVELOPE><BODY><DATA><COLLECTION>
<VOUCHER>
  <DATE>20260901</DATE>
  <VOUCHERNUMBER>5</VOUCHERNUMBER>
  <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
  <ALLLEDGERENTRIES.LIST><LEDGERNAME>Cash</LEDGERNAME><AMOUNT>1000</AMOUNT></ALLLEDGERENTRIES.LIST>
</VOUCHER>
</COLLECTION></DATA></BODY></ENVELOPE>"""
        client = TallyClient()
        client._get_daybook_remoteid_map = lambda: {}
        with patch("httpx.Client", return_value=_mock_client(xml)):
            txns = client.get_stock_transactions()
        assert len(txns) == 0

    def test_returns_empty_list_on_tally_error(self):
        """get_stock_transactions catches TallyError and returns []."""
        client = TallyClient()
        def raise_error(_xml):
            raise TallyError("TallyPrime error: timeout")
        client._post_xml = raise_error
        txns = client.get_stock_transactions()
        assert txns == []


# ─── Tests: stock items ───────────────────────────────────────────────────────

class TestGetStockItems:
    def test_parses_stock_items_with_group(self):
        """Name comes from XML attribute NAME=, group from child element PARENT."""
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_STOCK_XML)):
            items = client.get_stock_items()
        assert len(items) == 2
        assert items[0]["name"] == "Widget A"
        assert items[0]["stock_group"] == "Electronics"
        assert items[0]["unit"] == "Nos"

    def test_parses_remote_item_under_tablets(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_STOCK_XML)):
            items = client.get_stock_items()
        remote = next(i for i in items if i["name"] == "Remote")
        assert remote["stock_group"] == "Tablets"

    def test_skips_items_with_empty_name(self):
        xml = """<ENVELOPE><BODY><DATA><COLLECTION>
<STOCKITEM NAME="">
  <PARENT>Electronics</PARENT>
  <BASEUNITS>Nos</BASEUNITS>
</STOCKITEM>
</COLLECTION></DATA></BODY></ENVELOPE>"""
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(xml)):
            items = client.get_stock_items()
        assert len(items) == 0

    def test_primary_parent_normalized_to_none(self):
        xml = """<ENVELOPE><BODY><DATA><COLLECTION>
<STOCKITEM NAME="Ungrouped Item">
  <PARENT>Primary</PARENT>
  <BASEUNITS>Nos</BASEUNITS>
</STOCKITEM>
</COLLECTION></DATA></BODY></ENVELOPE>"""
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(xml)):
            items = client.get_stock_items()
        assert items[0]["stock_group"] is None


# ─── Tests: create vouchers ───────────────────────────────────────────────────

class TestCreateSalesVoucher:
    def test_creates_voucher_successfully(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_WRITE_OK_XML)):
            result = client.create_sales_voucher({
                "date": "20260814",
                "party_ledger": "ABC Traders",
                "sales_ledger": "Sales Account",
                "amount": "50000",
                "narration": "Test sale",
            })
        assert result["created"] == 1

    def test_raises_on_tally_line_error(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_ERROR_XML)):
            with pytest.raises(TallyError, match="Ledger not found"):
                client.create_sales_voucher({
                    "date": "20260814",
                    "party_ledger": "NONEXISTENT",
                    "amount": "100",
                })


class TestCreatePurchaseVoucher:
    def test_creates_purchase_voucher(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_WRITE_OK_XML)):
            result = client.create_purchase_voucher({
                "date": "20260814",
                "party_ledger": "Supplier Co",
                "purchase_ledger": "Purchase Account",
                "amount": "25000",
                "narration": "Office supplies",
            })
        assert result["created"] == 1


class TestCreateLedger:
    def test_creates_ledger(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_WRITE_OK_XML)):
            result = client.create_ledger({
                "name": "New Customer",
                "group": "Sundry Debtors",
                "opening_balance": "0",
            })
        assert result["created"] == 1


# ─── Tests: delete voucher ────────────────────────────────────────────────────

class TestDeleteVoucher:
    """
    delete_voucher() sends REMOTEID as an XML attribute on the VOUCHER element.
    This is the ONLY mechanism TallyPrime supports for XML-import-based deletion.

    Confirmed by live testing:
      • REMOTEID attribute → deleted=1 ✓
      • VOUCHERNUMBER attribute → "Cannot delete unnamed object: VOUCHER!" ✗
      • VOUCHERNUMBER child element → same error ✗
      • GUID as REMOTEID → "Voucher does not exist!" ✗
    """

    def test_deletes_by_fp_remoteid(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_DELETE_OK_XML)):
            result = client.delete_voucher({
                "voucher_ref": "FP-BA84BC6F2ADE",
                "voucher_type": "Receipt",
                "date": "20260901",
            })
        assert result["deleted"] == 1
        assert result["voucher_ref"] == "FP-BA84BC6F2ADE"

    def test_deletes_by_sj_remoteid(self):
        """Stock Journal delete must use SJ-xxx REMOTEID (not sequential VOUCHERNUMBER)."""
        client = TallyClient()
        posted_xml = []
        client._post_xml = lambda xml: (posted_xml.append(xml), SAMPLE_DELETE_OK_XML)[1]
        result = client.delete_voucher({
            "voucher_ref": "SJ-A8AC2842",
            "voucher_type": "Stock Journal",
            "date": "20260902",
        })
        assert result["deleted"] == 1
        xml = posted_xml[0]
        assert 'REMOTEID="SJ-A8AC2842"' in xml

    def test_deletes_by_ps_remoteid(self):
        """Physical Stock delete must use PS-xxx REMOTEID."""
        client = TallyClient()
        posted_xml = []
        client._post_xml = lambda xml: (posted_xml.append(xml), SAMPLE_DELETE_OK_XML)[1]
        result = client.delete_voucher({
            "voucher_ref": "PS-CCD0F9F0",
            "voucher_type": "Physical Stock",
            "date": "20260902",
        })
        assert result["deleted"] == 1
        assert 'REMOTEID="PS-CCD0F9F0"' in posted_xml[0]

    def test_deletes_by_voucher_number_when_no_remoteid(self):
        """Tally-native vouchers with no REMOTEID fall back to VOUCHERNUMBER child element."""
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_DELETE_OK_XML)):
            result = client.delete_voucher({
                "voucher_ref": "",
                "voucher_number": "TALLY-0004",
                "voucher_type": "Sales",
                "date": "20260901",
            })
        assert result["deleted"] == 1
        assert result["voucher_number"] == "TALLY-0004"

    def test_raises_when_tally_deletes_zero(self):
        """DELETED=0 means TallyPrime could not find the voucher."""
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_DELETE_ZERO_XML)):
            with pytest.raises(TallyError, match="did not delete"):
                client.delete_voucher({
                    "voucher_ref": "FP-nonexistent",
                    "voucher_type": "Sales",
                    "date": "20260901",
                })

    def test_raises_on_tally_line_error(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_ERROR_XML)):
            with pytest.raises(TallyError, match="Ledger not found"):
                client.delete_voucher({
                    "voucher_ref": "FP-001",
                    "voucher_type": "Sales",
                    "date": "20260901",
                })

    def test_raises_when_no_identifier_given(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_DELETE_OK_XML)):
            with pytest.raises(TallyError, match="voucher_ref.*or.*voucher_number is required"):
                client.delete_voucher({"voucher_type": "Sales"})

    def test_falls_back_to_today_when_no_date(self):
        """delete_voucher must not raise even if 'date' is missing — uses today."""
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_DELETE_OK_XML)):
            result = client.delete_voucher({
                "voucher_ref": "FP-002",
                "voucher_type": "Purchase",
            })
        assert result["deleted"] == 1

    def test_xml_uses_action_delete_not_cancel(self):
        """Verify the generated XML uses ACTION=Delete, not ACTION=Cancel."""
        client = TallyClient()
        posted_xml = []
        client._post_xml = lambda xml: (posted_xml.append(xml), SAMPLE_DELETE_OK_XML)[1]
        client.delete_voucher({
            "voucher_ref": "FP-xyz",
            "voucher_type": "Sales",
            "date": "20260901",
        })
        xml = posted_xml[0]
        assert 'ACTION="Delete"' in xml
        assert 'ACTION="Cancel"' not in xml
        assert 'ISCANCELLED' not in xml
        assert 'REMOTEID="FP-xyz"' in xml

    def test_xml_includes_fiscal_year_staticvariables(self):
        """DELETE XML must include SVFROMDATE/SVTODATE so TallyPrime searches the right period.
        Without this, TallyPrime returns 'Cannot delete unnamed object: VOUCHER!'."""
        client = TallyClient()
        posted_xml = []
        client._post_xml = lambda xml: (posted_xml.append(xml), SAMPLE_DELETE_OK_XML)[1]
        client.delete_voucher({
            "voucher_ref": "FP-xyz",
            "voucher_type": "Receipt",
            "date": "20260901",
        })
        xml = posted_xml[0]
        assert "SVFROMDATE" in xml, "Missing SVFROMDATE — TallyPrime can't locate voucher"
        assert "SVTODATE" in xml,   "Missing SVTODATE — TallyPrime can't locate voucher"

    def test_xml_uses_remoteid_attribute_not_vouchernumber_attribute(self):
        """Confirmed by live testing: VOUCHERNUMBER as attribute causes
        'Cannot delete unnamed object: VOUCHER!' regardless of FY context.
        Only REMOTEID attribute works."""
        client = TallyClient()
        posted_xml = []
        client._post_xml = lambda xml: (posted_xml.append(xml), SAMPLE_DELETE_OK_XML)[1]
        client.delete_voucher({
            "voucher_ref": "FP-abc",
            "voucher_type": "Receipt",
            "date": "20260901",
        })
        xml = posted_xml[0]
        assert 'REMOTEID="FP-abc"' in xml
        assert 'VOUCHERNUMBER="FP-abc"' not in xml

    def test_xml_uses_vouchernumber_as_child_element_for_tally_native(self):
        """For Tally-native vouchers (no FP-xxx REMOTEID in TallyPrime), VOUCHERNUMBER
        must be a child element (not XML attribute) — attribute form also fails."""
        client = TallyClient()
        posted_xml = []
        client._post_xml = lambda xml: (posted_xml.append(xml), SAMPLE_DELETE_OK_XML)[1]
        client.delete_voucher({
            "voucher_ref": "",
            "voucher_number": "19",
            "voucher_type": "Receipt",
            "date": "20260901",
        })
        xml = posted_xml[0]
        assert "<VOUCHERNUMBER>19</VOUCHERNUMBER>" in xml, \
            "VOUCHERNUMBER must be a child element, not an attribute"
        assert 'VOUCHERNUMBER="19"' not in xml, \
            "VOUCHERNUMBER as attribute causes 'unnamed object' error in TallyPrime"


# ─── Tests: error handling ────────────────────────────────────────────────────

class TestTimeout:
    def test_raises_tally_error_on_timeout(self):
        import httpx
        client = TallyClient()
        mock_http = _mock_client("")
        mock_http.post.side_effect = httpx.TimeoutException("timeout")
        with patch("httpx.Client", return_value=mock_http):
            with pytest.raises(TallyError, match="timed out"):
                client._post_xml("<test/>")


class TestMalformedXml:
    def test_raises_on_invalid_xml(self):
        bad_xml = "THIS IS NOT XML <<<>>>"
        client = TallyClient()
        with pytest.raises(TallyError, match="Invalid XML"):
            client._parse_response(bad_xml)

    def test_post_xml_returns_raw_text(self):
        response_xml = "<ENVELOPE><BODY></BODY></ENVELOPE>"
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(response_xml)):
            raw = client._post_xml("<ENVELOPE/>")
        assert raw == response_xml
