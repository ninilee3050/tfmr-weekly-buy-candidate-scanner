from __future__ import annotations

import http.client
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# US exchange lists, each sorted by market cap.  Together they hold every
# US-listed stock, including ADRs such as TSM, that can reach the Top 100.
# (StockAnalysis's "biggest companies" page became a world ranking with
# foreign home-market tickers, so it is no longer used.)
US_EXCHANGE_LIST_URLS = (
    "https://stockanalysis.com/list/nasdaq-stocks/",
    "https://stockanalysis.com/list/nyse-stocks/",
)
_MARKET_CAP_UNITS = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
TOP100_CACHE_PATH = Path("data") / "top100_cache.json"


class MarketCapLoadError(RuntimeError):
    """Raised when the live market-cap ranking cannot be loaded."""


@dataclass(frozen=True)
class MarketCapCompany:
    rank: int
    ticker: str
    company: str
    market_cap: str


@dataclass(frozen=True)
class Top100Result:
    """The ranking plus a warning when it is the saved copy, not a live one."""

    companies: list[MarketCapCompany]
    warning: str = ""


def fetch_us_top_market_cap(limit: int = 100) -> list[MarketCapCompany]:
    return fetch_us_top_market_cap_result(limit).companies


def fetch_us_top_market_cap_result(
    limit: int = 100,
    cache_path: Path | str | None = TOP100_CACHE_PATH,
) -> Top100Result:
    """Fetch the live ranking, falling back to the last saved one on failure.

    The ranking site changes its page layout from time to time.  When the live
    list cannot be read, the most recent successful list keeps the scan working
    and the warning says how old it is.
    """
    if limit <= 0:
        return Top100Result([])

    try:
        companies = _fetch_live_ranking(limit)
    except MarketCapLoadError as exc:
        cached = _load_ranking_cache(cache_path, limit)
        if cached is None:
            raise
        companies, saved_at = cached
        return Top100Result(
            companies,
            f"시가총액 순위를 새로 불러오지 못해 {saved_at}에 저장한 목록을 사용합니다. ({exc})",
        )
    _save_ranking_cache(cache_path, companies)
    return Top100Result(companies)


def _fetch_live_ranking(limit: int) -> list[MarketCapCompany]:
    listings: list[MarketCapCompany] = []
    for url in US_EXCHANGE_LIST_URLS:
        exchange_listings = parse_stockanalysis_market_cap_table(_download_list_page(url))
        if not exchange_listings:
            raise MarketCapLoadError(f"미국 시가총액 순위 목록을 찾지 못했습니다: {url}")
        listings.extend(exchange_listings)
    companies = common_stock_listings(rank_by_market_cap(listings))
    if not companies:
        raise MarketCapLoadError("미국 시가총액 순위 목록을 찾지 못했습니다.")
    return companies[:limit]


def rank_by_market_cap(listings: list[MarketCapCompany]) -> list[MarketCapCompany]:
    """Merge listings from several exchanges into one ranking by market cap."""
    ordered = sorted(
        listings,
        key=lambda item: market_cap_value(item.market_cap),
        reverse=True,
    )
    return [replace(item, rank=position) for position, item in enumerate(ordered, start=1)]


def market_cap_value(text: object) -> float:
    """"5.72T" -> 5.72e12; unreadable values sort last."""
    match = re.match(r"^\$?([\d,]*\.?\d+)\s*([KMBT])?$", str(text).strip().upper())
    if not match:
        return float("-inf")
    return float(match.group(1).replace(",", "")) * _MARKET_CAP_UNITS.get(match.group(2) or "", 1.0)


def _save_ranking_cache(
    cache_path: Path | str | None,
    companies: list[MarketCapCompany],
) -> None:
    if cache_path is None:
        return
    path = Path(cache_path)
    payload = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "companies": [asdict(company) for company in companies],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass  # The cache is only a fallback; the live list is still returned.


def load_saved_ranking(
    cache_path: Path | str | None = TOP100_CACHE_PATH,
) -> list[MarketCapCompany]:
    """The ranking saved by the last successful fetch, or an empty list."""
    cached = _load_ranking_cache(cache_path, limit=10_000)
    return cached[0] if cached else []


def _load_ranking_cache(
    cache_path: Path | str | None,
    limit: int,
) -> tuple[list[MarketCapCompany], str] | None:
    if cache_path is None:
        return None
    try:
        payload = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        companies = [MarketCapCompany(**item) for item in payload["companies"]]
        saved_at = str(payload["saved_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not companies:
        return None
    return companies[:limit], saved_at


def common_stock_listings(companies: list[MarketCapCompany]) -> list[MarketCapCompany]:
    """Keep one common-stock listing per company and renumber the ranks.

    The lists also carry preferred shares (e.g. ``BAC.PRO``) and second share
    classes (e.g. ``BRK.A``/``BRK.B``) with the whole company's market cap.
    Preferred shares are dropped.  Of a company's remaining listings the plain
    ticker is kept, or else the later share class (``BRK.B`` over ``BRK.A``),
    which is the class retail investors normally trade; it takes the
    company's first position so the ranking order is unchanged.
    """
    kept: list[MarketCapCompany] = []
    position_by_company: dict[str, int] = {}
    for company in sorted(companies, key=lambda item: item.rank):
        if _is_preferred_share(company.ticker):
            continue
        name = company.company.casefold()
        if name in position_by_company:
            index = position_by_company[name]
            if _share_class_preference(company.ticker) > _share_class_preference(kept[index].ticker):
                kept[index] = replace(company, rank=kept[index].rank)
            continue
        position_by_company[name] = len(kept)
        kept.append(replace(company, rank=len(kept) + 1))
    return kept


def _share_class_preference(ticker: str) -> tuple[int, str]:
    """Higher sorts first: a plain ticker, then the later share-class letter."""
    base, separator, share_class = ticker.upper().partition(".")
    return (1, "") if not separator else (0, share_class)


def _is_preferred_share(ticker: str) -> bool:
    """Preferred shares are listed as ``<ticker>.PR<series>``, e.g. MS.PRE."""
    _base, separator, suffix = ticker.upper().partition(".")
    return bool(separator) and suffix.startswith("PR")


def parse_stockanalysis_market_cap_table(html: str) -> list[MarketCapCompany]:
    parser = _TableParser()
    parser.feed(html)

    for table in parser.tables:
        companies = _companies_from_table(table)
        if companies:
            return companies
    return []


def _download_list_page(url: str) -> str:
    request = Request(
        url,
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
    except (OSError, http.client.HTTPException, ValueError) as exc:
        # Dropped connections and timeouts while reading are not URLErrors.
        raise MarketCapLoadError(
            f"StockAnalysis 접속 실패: {type(exc).__name__}"
        ) from exc


def _companies_from_table(table: list[list[str]]) -> list[MarketCapCompany]:
    if not table:
        return []

    header_index = None
    header = []
    for index, row in enumerate(table):
        normalized = [_normalize_header_cell(cell) for cell in row]
        if "market cap" in normalized and (
            {"symbol", "company name"} <= set(normalized)
            or {"rank", "company"} <= set(normalized)
        ):
            header_index = index
            header = normalized
            break

    if header_index is None:
        return []

    rank_index = _find_header_index(header, ["no.", "no", "#", "rank"])
    # Older layout: separate symbol and name columns.  Current layout: one
    # "Company" cell holding the name, the ticker and a link to the stock page.
    ticker_index = _find_header_index(header, ["symbol"])
    company_index = _find_header_index(header, ["company name", "company"])
    market_cap_index = _find_header_index(header, ["market cap"])

    if min(rank_index, company_index, market_cap_index) < 0:
        return []

    companies = []
    for row in table[header_index + 1 :]:
        if len(row) <= max(rank_index, ticker_index, company_index, market_cap_index):
            continue

        try:
            rank = int(_normalize_cell(row[rank_index]).replace(",", ""))
        except ValueError:
            continue

        if ticker_index >= 0:
            ticker = _normalize_ticker(row[ticker_index])
            company = _normalize_cell(row[company_index])
        else:
            ticker, company = _ticker_and_name_from_company_cell(row[company_index])
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


_STOCK_LINK_PATTERN = re.compile(r"^/stocks/([^/]+)/?$")


def _ticker_and_name_from_company_cell(cell: str) -> tuple[str, str]:
    """Split a combined cell such as "N | NVIDIA Corporation | NVDA".

    The ticker comes from the cell's /stocks/<ticker>/ link when present.  The
    leading single letter is the logo placeholder, not part of the name.
    """
    parts = [part for part in getattr(cell, "parts", ()) if part]
    links = getattr(cell, "links", ())
    ticker = ""
    for link in links:
        match = _STOCK_LINK_PATTERN.match(link)
        if match:
            ticker = _normalize_ticker(match.group(1))
            break
    if not ticker and parts:
        ticker = _normalize_ticker(parts[-1])
    if parts and _normalize_ticker(parts[-1]) == ticker:
        parts = parts[:-1]
    if len(parts) > 1 and len(parts[0]) == 1:
        parts = parts[1:]
    return ticker, " ".join(parts)


def _find_header_index(header: list[str], choices: list[str]) -> int:
    for choice in choices:
        if choice in header:
            return header.index(choice)
    return -1


def _normalize_cell(value: str) -> str:
    return " ".join(value.split()).strip()


def _normalize_header_cell(value: str) -> str:
    """Lower-case heading without a leading "#", so "# Rank" matches "rank"."""
    return _normalize_cell(value).lower().lstrip("#").strip()


def _normalize_ticker(value: str) -> str:
    return _normalize_cell(value).upper()


class _Cell(str):
    """A table cell's text that also keeps its text pieces and link targets."""

    parts: tuple[str, ...] = ()
    links: tuple[str, ...] = ()


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table_stack = 0
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._current_links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._table_stack += 1
            if self._table_stack == 1:
                self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"th", "td"} and self._current_row is not None:
            self._current_cell = []
            self._current_links = []
        elif tag == "a" and self._current_cell is not None:
            href = dict(attrs).get("href")
            if href:
                self._current_links.append(href)

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._current_cell is not None:
            assert self._current_row is not None
            # Pieces are joined with spaces so text from separate elements
            # ("NVIDIA Corporation", "NVDA") does not run together.
            cell = _Cell(_normalize_cell(" ".join(self._current_cell)))
            cell.parts = tuple(
                piece for piece in map(_normalize_cell, self._current_cell) if piece
            )
            cell.links = tuple(self._current_links)
            self._current_row.append(cell)
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
