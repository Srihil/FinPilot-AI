"""
Unit tests for TallyClient — no live TallyPrime required.
All HTTP calls are mocked.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent to path so we can import connector modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from tally_client import TallyClient, TallyError


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

SAMPLE_VOUCHER_XML = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<VOUCHER>
  <DATE>20260814</DATE>
  <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
  <NARRATION>Invoice 001</NARRATION>
  <PARTYLEDGERNAME>ABC Traders</PARTYLEDGERNAME>
  <AMOUNT>50000</AMOUNT>
</VOUCHER>
</COLLECTION></DATA></BODY>
</ENVELOPE>"""

SAMPLE_STOCK_XML = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<STOCKITEM>
  <NAME>Widget A</NAME>
  <BASEUNITS>Nos</BASEUNITS>
  <CLOSINGBALANCE>100</CLOSINGBALANCE>
  <CLOSINGRATE>250</CLOSINGRATE>
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


class TestGetVouchers:
    def test_parses_vouchers(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_VOUCHER_XML)):
            vouchers = client.get_vouchers()
        assert len(vouchers) == 1
        assert vouchers[0]["voucher_type"] == "Sales"
        assert vouchers[0]["party"] == "ABC Traders"

    def test_sales_filter(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_VOUCHER_XML)):
            sales = client.get_sales()
        assert len(sales) == 1
        assert "Sales" in sales[0]["voucher_type"]

    def test_purchases_filter_returns_empty_when_none(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_VOUCHER_XML)):
            purchases = client.get_purchases()
        assert len(purchases) == 0


class TestGetStockItems:
    def test_parses_stock_items(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_STOCK_XML)):
            items = client.get_stock_items()
        assert len(items) == 1
        assert items[0]["name"] == "Widget A"
        assert items[0]["unit"] == "Nos"
        assert items[0]["closing_balance"] == "100"


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


class TestDeleteVoucher:
    def test_deletes_by_remoteid(self):
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_DELETE_OK_XML)):
            result = client.delete_voucher({
                "voucher_ref": "FP-abc123",
                "voucher_type": "Sales",
                "date": "20260901",
            })
        assert result["deleted"] == 1
        assert result["voucher_ref"] == "FP-abc123"

    def test_deletes_by_voucher_number_when_no_remoteid(self):
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
        """TallyPrime returned DELETED=0 — voucher not found or wrong identifier."""
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(SAMPLE_DELETE_ZERO_XML)):
            with pytest.raises(TallyError, match="did not delete"):
                client.delete_voucher({
                    "voucher_ref": "FP-nonexistent",
                    "voucher_type": "Sales",
                    "date": "20260901",
                })

    def test_raises_on_tally_line_error(self):
        # _parse_response raises TallyError("TallyPrime error: ...") on LINEERROR
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
        """delete_voucher should not raise even if 'date' is missing — uses today."""
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

        def capture_post(xml):
            posted_xml.append(xml)
            return SAMPLE_DELETE_OK_XML

        client._post_xml = capture_post
        client.delete_voucher({
            "voucher_ref": "FP-xyz",
            "voucher_type": "Sales",
            "date": "20260901",
        })
        assert posted_xml, "No XML was posted"
        xml = posted_xml[0]
        assert 'ACTION="Delete"' in xml
        assert 'ACTION="Cancel"' not in xml
        assert 'ISCANCELLED' not in xml
        assert 'REMOTEID="FP-xyz"' in xml

    def test_xml_uses_vouchernumber_for_tally_native(self):
        """Verify the generated XML uses VOUCHERNUMBER when no REMOTEID."""
        client = TallyClient()
        posted_xml = []
        client._post_xml = lambda xml: (posted_xml.append(xml), SAMPLE_DELETE_OK_XML)[1]
        client.delete_voucher({
            "voucher_ref": "",
            "voucher_number": "TALLY-0004",
            "voucher_type": "Sales",
            "date": "20260901",
        })
        xml = posted_xml[0]
        assert 'VOUCHERNUMBER="TALLY-0004"' in xml
        assert 'REMOTEID' not in xml


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
        # _post_xml returns raw text; _parse_response is what raises on bad XML
        with pytest.raises(TallyError, match="Invalid XML"):
            client._parse_response(bad_xml)

    def test_post_xml_returns_raw_text(self):
        response_xml = "<ENVELOPE><BODY></BODY></ENVELOPE>"
        client = TallyClient()
        with patch("httpx.Client", return_value=_mock_client(response_xml)):
            raw = client._post_xml("<ENVELOPE/>")
        assert raw == response_xml
