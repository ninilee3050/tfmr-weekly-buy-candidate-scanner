"""Turning analysis tables into display text, row tags and card lines."""

from __future__ import annotations

from numbers import Real

import pandas as pd

from market_context import SP500_STATUS_COLUMN
from scanner import OUTCOME_SOLD
from scenario_tracker import (
    ADD_BUY_STAGE,
    FIRST_BUY_STAGE,
    PROVISIONAL_SELL_STATE,
    SELL_STAGE,
)
from watchlist import market_cap_rank_text
from gui.config import (
    MARKET_CAP_RANK_COLUMN,
    PRICE_COLUMNS,
    STRONG_RETURN_PERCENT,
    TRADE_HISTORY_DISPLAY_COLUMNS,
)


def scanner_table_for_display(
    data: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    display = data.copy()
    if MARKET_CAP_RANK_COLUMN in columns and "순위" in display.columns:
        display[MARKET_CAP_RANK_COLUMN] = display["순위"]
    return display.reindex(columns=columns)


def active_scenario_tag(state: object, rounds: object) -> str:
    """Row colour of a held case: sell pending, added to, or first buy only."""
    if state == PROVISIONAL_SELL_STATE:
        return "signal_third"
    number = pd.to_numeric(pd.Series([rounds]), errors="coerce").iloc[0]
    if pd.isna(number):
        return ""
    return "signal_second" if number >= 2 else "signal_first"


def history_case_tag(result: object, return_pct: object) -> str:
    """Colour a trade case by its realized return; held cases stay pale."""
    if str(result) != OUTCOME_SOLD:
        return "history_success_pending"
    value = pd.to_numeric(pd.Series([return_pct]), errors="coerce").iloc[0]
    if pd.isna(value):
        return ""
    if value > 0:
        return (
            "history_success_high"
            if value >= STRONG_RETURN_PERCENT
            else "history_success_medium"
        )
    if value < 0:
        return (
            "history_loss_high"
            if value <= -STRONG_RETURN_PERCENT
            else "history_loss_medium"
        )
    return "history_flat"


def scan_event_priority(stage: object) -> int:
    """Sells first, then add-on buys, then new first buys."""
    return {SELL_STAGE: 0, ADD_BUY_STAGE: 1, FIRST_BUY_STAGE: 2}.get(stage, 3)


def scan_event_tag(stage: object) -> str:
    return {
        0: "signal_third",
        1: "signal_second",
        2: "signal_first",
    }.get(scan_event_priority(stage), "")


def dashboard_summary(
    events: pd.DataFrame,
    active_scenarios: pd.DataFrame,
    has_scan_results: bool,
) -> dict[str, tuple[str, str, bool]]:
    """Return (value, note, alert) for each dashboard card."""
    summary: dict[str, tuple[str, str, bool]] = {}
    stages = (
        events["단계"]
        if not events.empty and "단계" in events.columns
        else pd.Series(dtype=object)
    )
    cards = (
        ("first", FIRST_BUY_STAGE, "새 1회차 매수 후보"),
        ("add", ADD_BUY_STAGE, "직전 매수가 대비 3% 이상 하락"),
        ("sell", SELL_STAGE, "양봉 + 5주선 또는 20주선 위"),
    )
    for key, stage, note in cards:
        if not has_scan_results:
            summary[key] = ("스캔 전", "통합 스캔 후 표시됩니다", False)
            continue
        count = int((stages == stage).sum())
        summary[key] = (f"{count}건", note, count > 0)

    states = (
        active_scenarios["현재상태"]
        if not active_scenarios.empty and "현재상태" in active_scenarios.columns
        else pd.Series(dtype=object)
    )
    pending = int((states == PROVISIONAL_SELL_STATE).sum())
    summary["holding"] = (
        f"{len(active_scenarios)}건",
        f"매도 신호 잠정 {pending}건" if pending else "매도 신호 대기 중",
        False,
    )
    return summary


def trade_summary_cards(cases: pd.DataFrame | None) -> dict[str, tuple[str, str]]:
    """Return (value, note) for the selected ticker's three summary cards."""
    if cases is None:
        return {"closed": ("-", ""), "win": ("-", ""), "average": ("-", "")}
    sold = cases[cases["Outcome"] == OUTCOME_SOLD] if not cases.empty else cases
    holding = len(cases) - len(sold)
    holding_note = f"보유 중 {holding}건" if holding else "보유 중 없음"
    if sold.empty:
        return {
            "closed": ("0건", holding_note),
            "win": ("미산출", "매도 완료 없음"),
            "average": ("미산출", ""),
        }
    returns = pd.to_numeric(sold["ReturnPct"], errors="coerce")
    wins = int((returns > 0).sum())
    weeks = pd.to_numeric(sold["HoldingWeeks"], errors="coerce").mean()
    return {
        "closed": (f"{len(sold)}건", holding_note),
        "win": (f"{wins / len(sold) * 100:.1f}%", f"{len(sold)}건 중 {wins}건 수익"),
        "average": (f"{returns.mean():+.2f}%", f"평균 {weeks:.1f}주 보유"),
    }


def trade_cases_for_display(data: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "FirstBuyDate": "1차매수일",
        "BuyRounds": "매수차수",
        "LastBuyDate": "최근매수일",
        "AveragePrice": "평단가",
        "SellDate": "매도일",
        "SellPrice": "매도가",
        "Outcome": "결과",
        "ReturnPct": "수익률",
        "HoldingWeeks": "보유주수",
    }
    display = data.rename(columns=rename_map).copy()
    if SP500_STATUS_COLUMN not in display.columns:
        display[SP500_STATUS_COLUMN] = ""
    return display.reindex(columns=TRADE_HISTORY_DISPLAY_COLUMNS)


def _format_value(value: object, column: str = "") -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if column == MARKET_CAP_RANK_COLUMN and not isinstance(value, str):
        return market_cap_rank_text(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    # numpy numbers read back from a table count as numbers too.
    if isinstance(value, Real):
        if column == "매수차수":
            return f"{int(value)}차"
        if column == "보유주수":
            return f"{int(value)}주"
        if column.endswith("수익률") or column.endswith("손익률"):
            return f"{value:+.2f}%"
        if column in PRICE_COLUMNS:
            return f"{value:,.2f}"
        if not float(value).is_integer():
            return f"{value:.4f}"
    return str(value)
