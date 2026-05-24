from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


STOCK_ANALYSIS_BIGGEST_COMPANIES_URL = "https://stockanalysis.com/list/biggest-companies/"


class MarketCapLoadError(RuntimeError):
    """Raised when the live market-cap ranking cannot be loaded."""


@dataclass(frozen=True)
class MarketCapCompany:
    rank: int
    ticker: str
    company: str
    market_cap: str


def fetch_us_top_market_cap(limit: int = 100) -> list[MarketCapCompany]:
    if limit <= 0:
        return []

    try:
        html = _download_stockanalysis_page()
        companies = parse_stockanalysis_market_cap_table(html)
    except MarketCapLoadError:
        raise
    except Exception as exc:
        raise MarketCapLoadError(
            "Top100 목록을 불러오지 못했습니다. 인터넷 연결 또는 사이트 응답을 확인해 주세요."
        ) from exc

    if not companies:
        raise MarketCapLoadError(
            "Top100 목록을 불러오지 못했습니다. 인터넷 연결 또는 사이트 응답을 확인해 주세요."
        )
    return companies[:limit]


def parse_stockanalysis_market_cap_table(html: str) -> list[MarketCapCompany]:
    parser = _TableParser()
    parser.feed(html)

    for table in parser.tables:
        companies = _companies_from_table(table)
        if companies:
            return companies
    return []


def _download_stockanalysis_page() -> str:
    request = Request(
        STOCK_ANALYSIS_BIGGEST_COMPANIES_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise MarketCapLoadError(f"StockAnalysis 접속 실패: HTTP {exc.code}") from exc
    except URLError as exc:
        raise MarketCapLoadError(f"StockAnalysis 접속 실패: {exc.reason}") from exc


def _companies_from_table(table: list[list[str]]) -> list[MarketCapCompany]:
    if not table:
        return []

    header_index = None
    header = []
    for index, row in enumerate(table):
        normalized = [_normalize_cell(cell).lower() for cell in row]
        if "symbol" in normalized and "company name" in normalized and "market cap" in normalized:
            header_index = index
            header = normalized
            break

    if header_index is None:
        return []

    rank_index = _find_header_index(header, ["no.", "no", "#"])
    ticker_index = _find_header_index(header, ["symbol"])
    company_index = _find_header_index(header, ["company name", "company"])
    market_cap_index = _find_header_index(header, ["market cap"])

    if min(rank_index, ticker_index, company_index, market_cap_index) < 0:
        return []

    companies = []
    for row in table[header_index + 1 :]:
        if len(row) <= max(rank_index, ticker_index, company_index, market_cap_index):
            continue

        try:
            rank = int(_normalize_cell(row[rank_index]).replace(",", ""))
        except ValueError:
            continue

        ticker = _normalize_ticker(row[ticker_index])
        company = _normalize_cell(row[company_index])
        market_cap = _normalize_cell(row[market_cap_index])
        if ticker and company and market_cap:
            companies.append(
                MarketCapCompany(
                    rank=rank,
                    ticker=ticker,
                    company=company,
                    market_cap=market_cap,
                )
            )
    return companies


def _find_header_index(header: list[str], choices: list[str]) -> int:
    for choice in choices:
        if choice in header:
            return header.index(choice)
    return -1


def _normalize_cell(value: str) -> str:
    return " ".join(value.split()).strip()


def _normalize_ticker(value: str) -> str:
    return _normalize_cell(value).upper()


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table_stack = 0
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._table_stack += 1
            if self._table_stack == 1:
                self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"th", "td"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._current_cell is not None:
            assert self._current_row is not None
            self._current_row.append(_normalize_cell("".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            assert self._current_table is not None
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._table_stack:
            self._table_stack -= 1
            if self._table_stack == 0 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None
