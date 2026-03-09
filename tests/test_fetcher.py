from pathlib import Path

import pytest

from src.fetcher import (
    No13FFilingError,
    SecEdgarClient,
    fetch_latest_13f_metadata,
    normalize_cik,
    parse_infotable_xml,
)


def test_parser_infotable_xml() -> None:
    xml = Path("tests/fixtures/infotable_sample.xml").read_text(encoding="utf-8")
    df = parse_infotable_xml(xml)

    assert len(df) > 0
    assert df["issuer"].notna().all()
    assert df["cusip"].notna().all()
    assert df["value"].sum() > 0


def test_cik_padding() -> None:
    assert normalize_cik("1234") == "0000001234"


def test_fetch_latest_13f_metadata_no_13f(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResponse:
        def json(self):
            return {
                "cik": "1234",
                "name": "Test Institution",
                "filings": {
                    "recent": {
                        "form": ["10-K"],
                        "accessionNumber": ["0000000000-00-000001"],
                        "filingDate": ["2025-01-01"],
                        "reportDate": ["2024-12-31"],
                    }
                },
            }

    def fake_get(self, url: str, host: str = "data.sec.gov"):
        return DummyResponse()

    monkeypatch.setattr(SecEdgarClient, "get", fake_get)
    client = SecEdgarClient(user_agent="TestApp test@example.com")

    with pytest.raises(No13FFilingError):
        fetch_latest_13f_metadata(client, "1234")
