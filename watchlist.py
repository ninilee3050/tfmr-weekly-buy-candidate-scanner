"""User watchlist: extra tickers scanned together with the Top 100.

``watchlist.txt`` holds one ticker per line, optionally followed by a comma
and a display name ("BTC-USD, 비트코인").  Lines starting with ``#`` are
comments.  The GUI scan and the headless weekly scan both read this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data_provider import is_weekend_traded
from market_cap_provider import MarketCapCompany


WATCHLIST_PATH = Path("watchlist.txt")
# Watchlist entries sort after every ranked company.
WATCHLIST_RANK_START = 9000
# Rank kept for a tracked ticker that is no longer in the Top 100.
OUT_OF_RANKING_RANK = 9999
WATCHLIST_LABEL = "[관심]"
WATCHLIST_FILE_HEADER = (
    "# 관심종목: 통합 스캔과 금요일 자동 스캔에 Top 100과 함께 포함됩니다.\n"
    "# 한 줄에 하나씩 '티커, 이름' 형식으로 적습니다. 이름은 생략할 수 있습니다.\n"
)


@dataclass(frozen=True)
class WatchlistItem:
    ticker: str
    name: str = ""

    @property
    def display_name(self) -> str:
        return self.name or self.ticker


def market_cap_rank_text(rank: object) -> str:
    """Display text for a company's rank: "8위", "관심" or "순위 밖".

    Watchlist entries carry ranks from ``WATCHLIST_RANK_START``; a tracked
    ticker that has left the ranking carries the out-of-ranking default.
    """
    number = pd.to_numeric(pd.Series([rank]), errors="coerce").iloc[0]
    if pd.isna(number):
        return ""
    number = int(number)
    if number < WATCHLIST_RANK_START:
        return f"{number}위"
    if number < OUT_OF_RANKING_RANK:
        return "관심"
    return "순위 밖"


def load_watchlist(path: Path | str = WATCHLIST_PATH) -> list[WatchlistItem]:
    """Read the watchlist; a missing file means an empty list."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return []
    items: list[WatchlistItem] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ticker, _separator, name = line.partition(",")
        ticker = normalize_watchlist_ticker(ticker)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        items.append(WatchlistItem(ticker, name.strip()))
    return items


def save_watchlist(
    items: list[WatchlistItem],
    path: Path | str = WATCHLIST_PATH,
) -> None:
    destination = Path(path)
    lines = [
        f"{item.ticker}, {item.name}" if item.name else item.ticker
        for item in items
    ]
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        WATCHLIST_FILE_HEADER + "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )
    temporary.replace(destination)


def normalize_watchlist_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def add_watchlist_item(
    items: list[WatchlistItem],
    ticker: str,
    name: str = "",
) -> list[WatchlistItem]:
    """Return the list with one more ticker; reject blanks and duplicates."""
    normalized = normalize_watchlist_ticker(ticker)
    if not normalized:
        raise ValueError("티커를 입력해 주세요.")
    if any(char.isspace() or char == "," for char in normalized):
        raise ValueError("티커에는 빈칸이나 쉼표를 넣을 수 없습니다.")
    if any(item.ticker == normalized for item in items):
        raise ValueError(f"{normalized}은(는) 이미 관심종목에 있습니다.")
    return [*items, WatchlistItem(normalized, name.strip())]


def remove_watchlist_item(
    items: list[WatchlistItem],
    ticker: str,
) -> list[WatchlistItem]:
    normalized = normalize_watchlist_ticker(ticker)
    return [item for item in items if item.ticker != normalized]


def watchlist_companies(
    items: list[WatchlistItem],
    ranked_companies: list[MarketCapCompany],
) -> list[MarketCapCompany]:
    """Watchlist entries to scan in addition to the ranked companies.

    A ticker that is already ranked is scanned once, as the ranked company.
    """
    ranked = {company.ticker.upper() for company in ranked_companies}
    companies = []
    for position, item in enumerate(items):
        if item.ticker in ranked:
            continue
        companies.append(
            MarketCapCompany(
                rank=WATCHLIST_RANK_START + position,
                ticker=item.ticker,
                company=f"{WATCHLIST_LABEL} {item.display_name}",
                market_cap="",
            )
        )
    return companies
