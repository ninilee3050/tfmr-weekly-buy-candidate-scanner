"""Assembling and ordering scan and history results."""

from __future__ import annotations

import pandas as pd

from market_cap_provider import MarketCapCompany
from market_context import annotate_sp500_status
from scanner import OUTCOME_SOLD
from scenario_tracker import PROVISIONAL_SELL_STATE
from gui.config import (
    CLOSED_SCENARIO_DISPLAY_COLUMNS,
    MARKET_CAP_RANK_COLUMN,
    TRADE_HISTORY_DISPLAY_COLUMNS,
)
from gui.formatting import scan_event_priority, trade_cases_for_display


def _failure_row(company: MarketCapCompany, error: str) -> dict[str, object]:
    return {
        "순위": company.rank,
        "티커": company.ticker,
        "회사명": company.company,
        "시가총액": company.market_cap,
        "오류": error,
    }


def prioritize_scan_events(data: pd.DataFrame) -> pd.DataFrame:
    """Put the most urgent signals first, then recency and market-cap order."""
    display = data.copy()
    if display.empty:
        return display
    display["_신호우선순위"] = display["단계"].map(scan_event_priority)
    return (
        display.sort_values(
            by=["_신호우선순위", "신호일", "순위"],
            ascending=[True, False, True],
            na_position="last",
        )
        .drop(columns=["_신호우선순위"])
        .reset_index(drop=True)
    )


def prioritize_active_scenarios(data: pd.DataFrame) -> pd.DataFrame:
    """Pending sells first, then the cases bought most often, then by rank."""
    display = data.copy()
    if display.empty:
        return display
    display["_매도대기"] = display["현재상태"].ne(PROVISIONAL_SELL_STATE)
    display["_차수"] = pd.to_numeric(display.get("매수차수"), errors="coerce")
    return (
        display.sort_values(
            by=["_매도대기", "_차수", "순위", "티커"],
            ascending=[True, False, True, True],
            na_position="last",
        )
        .drop(columns=["_매도대기", "_차수"])
        .reset_index(drop=True)
    )


def build_closed_scenario_history(
    companies: list[MarketCapCompany],
    cases_by_ticker: dict[str, pd.DataFrame],
    previous: pd.DataFrame | None = None,
    failed_tickers: set[str] | None = None,
) -> pd.DataFrame:
    """Every sold case of the current Top 100, newest first.

    Tickers whose data failed this scan keep the rows saved by the last scan.
    """
    frames: list[pd.DataFrame] = []
    current_tickers = {company.ticker.upper() for company in companies}

    for company in companies:
        cases = cases_by_ticker.get(company.ticker.upper())
        if cases is None or cases.empty or "Outcome" not in cases.columns:
            continue
        sold = cases.loc[cases["Outcome"] == OUTCOME_SOLD]
        if sold.empty:
            continue
        display = trade_cases_for_display(sold)
        display.insert(0, "회사명", company.company)
        display.insert(0, "티커", company.ticker.upper())
        display.insert(0, MARKET_CAP_RANK_COLUMN, company.rank)
        frames.append(display)

    if frames:
        current = pd.concat(frames, ignore_index=True)
    else:
        current = pd.DataFrame(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)

    failed = {ticker.upper() for ticker in (failed_tickers or set())}
    if previous is not None and not previous.empty and failed:
        previous_tickers = previous["티커"].astype(str).str.upper()
        preserved = previous.loc[
            previous_tickers.isin(failed & current_tickers)
        ].copy()
        current = pd.concat([current, preserved], ignore_index=True)

    if current.empty:
        return pd.DataFrame(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)

    current = current.reindex(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)
    for column in ("1차매수일", "매도일"):
        current[column] = pd.to_datetime(current[column], errors="coerce")
    return (
        current.drop_duplicates(subset=["티커", "1차매수일"], keep="first")
        .sort_values(
            by=["1차매수일", MARKET_CAP_RANK_COLUMN, "티커"],
            ascending=[False, True, True],
            na_position="last",
        )
        .reset_index(drop=True)
    )


def trade_history_display(
    cases: pd.DataFrame,
    sp500_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One ticker's cases as shown in the history table, with the market state.

    A sold case uses the S&P 500 state of its sell week; a held case uses the
    latest state.
    """
    annotated = annotate_sp500_status(
        trade_cases_for_display(cases),
        sp500_data if sp500_data is not None else pd.DataFrame(),
        reference_date_columns=("매도일",),
    )
    return annotated.reindex(columns=TRADE_HISTORY_DISPLAY_COLUMNS)


def trade_case_position(
    cases: pd.DataFrame,
    case: pd.Series | None,
) -> int | None:
    """Return the row position of a chart case within the ticker's cases."""
    if cases.empty or case is None or "FirstBuyDate" not in cases.columns:
        return None
    target = pd.to_datetime(case.get("FirstBuyDate"), errors="coerce")
    if pd.isna(target):
        return None
    dates = pd.to_datetime(cases["FirstBuyDate"], errors="coerce").dt.normalize()
    positions = [
        position
        for position, matched in enumerate(dates.eq(pd.Timestamp(target).normalize()))
        if matched
    ]
    return positions[-1] if positions else None


def _sorted_frame(
    rows: list[dict[str, object]],
    columns: list[str],
    by: list[str],
    ascending: list[bool],
) -> pd.DataFrame:
    data = pd.DataFrame(rows, columns=columns)
    if data.empty:
        return data
    return data.sort_values(by=by, ascending=ascending, na_position="last").reset_index(drop=True)
