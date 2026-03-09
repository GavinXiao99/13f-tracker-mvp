"""SEC EDGAR fetch and parse helpers for 13F ingestion."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
import requests
from lxml import etree, html

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession_no_dash}/"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SecEdgarError(Exception):
    """Base SEC EDGAR error."""


class No13FFilingError(SecEdgarError):
    """Raised when no 13F filing is available for a CIK."""


class SecRateLimiter:
    """Global process-level rate limiter to keep SEC requests <= 10 rps."""

    _lock = threading.Lock()
    _calls: deque[float] = deque()

    def __init__(self, max_calls: int = 10, period_seconds: float = 1.0) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.period_seconds:
                    self._calls.popleft()
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                wait = self.period_seconds - (now - self._calls[0])
            time.sleep(max(wait, 0.01))


@dataclass
class FilingMetadata:
    institution_name: str
    cik: str
    accession: str
    filing_date: str
    report_period: str | None


class SecEdgarClient:
    """HTTP client with SEC-required headers, throttling, timeout and retries."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: int = 15,
        max_retries: int = 4,
        limiter: SecRateLimiter | None = None,
    ) -> None:
        if not user_agent:
            raise ValueError("SEC user agent is required.")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.limiter = limiter or SecRateLimiter()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Host": "data.sec.gov",
            }
        )

    def get(self, url: str, host: str = "data.sec.gov") -> requests.Response:
        headers = {"Host": host}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            try:
                response = self.session.get(url, timeout=self.timeout_seconds, headers=headers)
                if response.status_code in RETRYABLE_STATUS:
                    if attempt >= self.max_retries:
                        response.raise_for_status()
                    backoff = min(2**attempt, 8)
                    time.sleep(backoff)
                    continue
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                backoff = min(2**attempt, 8)
                time.sleep(backoff)
        raise SecEdgarError(f"Request failed for {url}: {last_error}")


def normalize_cik(cik_input: str) -> str:
    digits = re.sub(r"\D", "", cik_input or "")
    if not digits:
        raise ValueError("CIK 不能为空。")
    return digits.zfill(10)


def health_check_dependencies() -> dict[str, str]:
    return {
        "requests": requests.__version__,
        "pandas": pd.__version__,
        "lxml": etree.LXML_VERSION.__str__(),
    }


def _extract_recent_13f(submissions: dict[str, Any]) -> FilingMetadata:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])

    rows: list[tuple[str, str, str, str | None]] = []
    for form, accession, filing_date, report_date in zip(
        forms, accession_numbers, filing_dates, report_dates
    ):
        if form in {"13F-HR", "13F-HR/A"}:
            rows.append((form, accession, filing_date, report_date or None))

    if not rows:
        raise No13FFilingError("该 CIK 暂无 13F-HR / 13F-HR/A 申报。")

    rows.sort(key=lambda item: datetime.fromisoformat(item[2]), reverse=True)
    _, accession, filing_date, report_period = rows[0]
    return FilingMetadata(
        institution_name=submissions.get("name", "Unknown Institution"),
        cik=normalize_cik(str(submissions.get("cik", ""))),
        accession=accession,
        filing_date=filing_date,
        report_period=report_period,
    )


def _find_infotable_from_index_json(index_payload: dict[str, Any]) -> str | None:
    items = index_payload.get("directory", {}).get("item", [])
    candidates = [
        item.get("name", "")
        for item in items
        if "infotable" in item.get("name", "").lower()
        and item.get("name", "").lower().endswith(".xml")
    ]
    if candidates:
        return sorted(candidates)[0]

    xml_candidates = [
        item.get("name", "")
        for item in items
        if item.get("name", "").lower().endswith(".xml")
    ]
    return sorted(xml_candidates)[0] if xml_candidates else None


def _find_infotable_from_html(index_html: str) -> str | None:
    tree = html.fromstring(index_html)
    links = tree.xpath("//a/@href")
    normalized = [link.split("/")[-1] for link in links if link]
    preferred = [
        link for link in normalized if "infotable" in link.lower() and link.lower().endswith(".xml")
    ]
    if preferred:
        return sorted(preferred)[0]
    fallback = [link for link in normalized if link.lower().endswith(".xml")]
    return sorted(fallback)[0] if fallback else None


def fetch_latest_13f_metadata(client: SecEdgarClient, cik: str) -> FilingMetadata:
    normalized_cik = normalize_cik(cik)
    response = client.get(SUBMISSIONS_URL.format(cik=normalized_cik), host="data.sec.gov")
    submissions = response.json()
    return _extract_recent_13f(submissions)


def download_latest_infotable_xml(client: SecEdgarClient, metadata: FilingMetadata) -> str:
    accession_no_dash = metadata.accession.replace("-", "")
    cik_num = str(int(metadata.cik))
    base_url = ARCHIVES_BASE_URL.format(cik_num=cik_num, accession_no_dash=accession_no_dash)

    try:
        index_resp = client.get(f"{base_url}index.json", host="www.sec.gov")
        filename = _find_infotable_from_index_json(index_resp.json())
    except Exception:
        filename = None

    if not filename:
        html_url = f"{base_url}{metadata.accession}-index.html"
        html_resp = client.get(html_url, host="www.sec.gov")
        filename = _find_infotable_from_html(html_resp.text)

    if not filename:
        raise SecEdgarError("未在 filing 目录中定位到 infotable XML。")

    xml_resp = client.get(f"{base_url}{filename}", host="www.sec.gov")
    return xml_resp.text


def _get_text(node: etree._Element | None, field_name: str) -> str | None:
    if node is None:
        return None
    values = node.xpath(f'.//*[local-name()="{field_name}"]/text()')
    if not values:
        return None
    value = values[0].strip()
    return value if value else None


def parse_infotable_xml(xml_content: str) -> pd.DataFrame:
    root = etree.fromstring(xml_content.encode("utf-8"))
    rows = []
    for info in root.xpath('.//*[local-name()="infoTable"]'):
        voting = info.xpath('./*[local-name()="votingAuthority"]')
        voting_node = voting[0] if voting else None

        rows.append(
            {
                "issuer": _get_text(info, "nameOfIssuer"),
                "cusip": _get_text(info, "cusip"),
                "value": int(_get_text(info, "value") or 0),
                "sshPrnamt": int(_get_text(info, "sshPrnamt") or 0),
                "sshPrnamtType": _get_text(info, "sshPrnamtType"),
                "putCall": _get_text(info, "putCall"),
                "investmentDiscretion": _get_text(info, "investmentDiscretion"),
                "votingSole": int(_get_text(voting_node, "Sole") or 0) if voting_node is not None else 0,
                "votingShared": int(_get_text(voting_node, "Shared") or 0) if voting_node is not None else 0,
                "votingNone": int(_get_text(voting_node, "None") or 0) if voting_node is not None else 0,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by="value", ascending=False).reset_index(drop=True)
    return df
