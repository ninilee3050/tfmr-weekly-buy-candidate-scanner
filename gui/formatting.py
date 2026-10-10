"""Turning analysis tables into display text, row tags and card lines."""

from __future__ import annotations

import pandas as pd

from performance_analytics import format_rate, format_reach_rate
from watchlist import market_cap_rank_text
from gui.config import (
    MARKET_CAP_RANK_COLUMN,
    FIELD_DISPLAY_COLUMNS,
    RANKING_DISPLAY_COLUMNS,
    SIGNAL_HISTORY_DISPLAY_COLUMNS,
    SIGNAL_VALIDATION_DISPLAY_COLUMNS,
)


def table_for_display(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data.reset_index().rename(columns={"Date": "매수포인트날짜"})
    display = data.reset_index()
    if "Date" not in display.columns:
        display = display.rename(columns={display.columns[0]: "Date"})
    display = display.rename(columns={"Date": "매수포인트날짜"})
    return display


def scanner_table_for_display(
    data: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    display = data.copy()
    if MARKET_CAP_RANK_COLUMN in columns and "순위" in display.columns:
        display[MARKET_CAP_RANK_COLUMN] = display["순위"]
    return display.reindex(columns=columns)


def active_scenario_tag(state: object) -> str:
    if state == "3차 신호 대기":
        return "signal_second"
    if state == "2차 신호 대기":
        return "signal_first"
    return ""


def history_cycle_tag(result: object, *horizon_returns: object) -> str:
    """Color a completed cycle by multi-horizon consistency and maturity."""
    result_text = str(result)
    if "폐기" in result_text:
        return "history_discard"
    if result_text == "실패":
        return "history_failure"
    if result_text != "매수 성공":
        return ""

    numeric_returns = pd.to_numeric(
        pd.Series(horizon_returns, dtype=object), errors="coerce"
    ).dropna()
    confirmed_count = len(numeric_returns)
    if confirmed_count == 0:
        return "history_success_pending"

    positive_count = int((numeric_returns > 0).sum())
    negative_count = int((numeric_returns < 0).sum())

    if positive_count == confirmed_count:
        if confirmed_count == 4:
            return "history_success_high"
        if confirmed_count == 3:
            return "history_success_medium"
        return "history_success_low"

    if negative_count == confirmed_count:
        if confirmed_count == 4:
            return "history_loss_high"
        if confirmed_count == 3:
            return "history_loss_medium"
        return "history_loss_low"

    if confirmed_count == 4:
        if positive_count == 3:
            return "history_success_medium"
        if positive_count == 2:
            return "history_flat"
        if positive_count == 1 and negative_count > positive_count:
            return "history_loss_low"

    if positive_count > negative_count:
        return "history_success_low"
    if negative_count > positive_count:
        return "history_loss_low"
    if positive_count == negative_count:
        return "history_flat"
    return "history_success_pending"


def scan_event_priority(stage: object, result: object) -> int:
    if stage == "3차 신호" and result == "매수 성공":
        return 0
    if stage == "2차 신호":
        return 1
    if stage == "1차 신호":
        return 2
    return 3


def scan_event_tag(stage: object, result: object) -> str:
    priority = scan_event_priority(stage, result)
    return {
        0: "signal_third",
        1: "signal_second",
        2: "signal_first",
    }.get(priority, "")


def field_performance_for_display(data: pd.DataFrame) -> pd.DataFrame:
    display = data.copy()
    if display.empty:
        return pd.DataFrame(columns=FIELD_DISPLAY_COLUMNS)
    display["매수 도달률"] = display.apply(
        lambda row: format_reach_rate(
            row["매수 도달률"], row["매수 건수"], row["종료 사이클"]
        ),
        axis=1,
    )
    display["승률"] = display.apply(
        lambda row: format_rate(row["승률"], row["승리"], row["분석 표본"]),
        axis=1,
    )
    _format_benchmark_rates(display)
    return display.reindex(columns=FIELD_DISPLAY_COLUMNS)


def ranking_for_display(data: pd.DataFrame) -> pd.DataFrame:
    display = data.copy()
    if display.empty:
        return pd.DataFrame(columns=RANKING_DISPLAY_COLUMNS)
    display["매수 도달률"] = display.apply(
        lambda row: format_reach_rate(
            row["매수 도달률"], row["매수 건수"], row["종료 사이클"]
        ),
        axis=1,
    )
    display["승률"] = display.apply(
        lambda row: format_rate(row["승률"], row["승리"], row["분석 표본"]),
        axis=1,
    )
    return display.reindex(columns=RANKING_DISPLAY_COLUMNS)


def signal_validation_for_display(data: pd.DataFrame) -> pd.DataFrame:
    display = data.copy()
    if display.empty:
        return pd.DataFrame(columns=SIGNAL_VALIDATION_DISPLAY_COLUMNS)
    display["승률"] = display.apply(
        lambda row: format_rate(row["승률"], row["승리"], row["분석 표본"]),
        axis=1,
    )
    _format_benchmark_rates(display)
    return display.reindex(columns=SIGNAL_VALIDATION_DISPLAY_COLUMNS)


def _format_benchmark_rates(display: pd.DataFrame) -> None:
    """Turn the baseline win rates into text in place (skipped when absent)."""
    if "평소 매수 승률" in display.columns:
        display["평소 매수 승률"] = display["평소 매수 승률"].map(
            lambda value: "미산출" if pd.isna(value) else f"{float(value):.1f}%"
        )
    required = {"S&P 이긴 비율", "S&P 이긴 건수", "S&P 비교 표본"}
    if not required.issubset(display.columns):
        return
    display["S&P 이긴 비율"] = display.apply(
        lambda row: format_rate(
            row["S&P 이긴 비율"], row["S&P 이긴 건수"], row["S&P 비교 표본"]
        ),
        axis=1,
    )


def dashboard_summary(
    events: pd.DataFrame,
    active_scenarios: pd.DataFrame,
    has_scan_results: bool,
    last_scan_date: pd.Timestamp | None,
    today: pd.Timestamp,
    last_scan_time: pd.Timestamp | None = None,
    now: pd.Timestamp | None = None,
) -> dict[str, tuple[str, str, bool]]:
    """Return (value, note, alert) for each dashboard card.

    ``last_scan_time`` (local clock) is preferred for the last-scan card when
    known; otherwise the card falls back to ``last_scan_date``.
    """
    summary: dict[str, tuple[str, str, bool]] = {}

    if not has_scan_results:
        summary["buy"] = ("스캔 전", "통합 스캔 후 표시됩니다", False)
    else:
        bought = pd.Series(False, index=events.index)
        if not events.empty and {"단계", "결과"}.issubset(events.columns):
            bought = (events["단계"] == "3차 신호") & (events["결과"] == "매수 성공")
        count = int(bought.sum())
        priority = 0
        if count and "검토등급" in events.columns:
            priority = int((bought & (events["검토등급"] == "우선검토")).sum())
        note = f"우선검토 {priority}건" if count else "이번 스캔 매수 신호 없음"
        summary["buy"] = (f"{count}건", note, count > 0)

    states = (
        active_scenarios["현재상태"]
        if not active_scenarios.empty and "현재상태" in active_scenarios.columns
        else pd.Series(dtype=object)
    )
    summary["wait3"] = (
        f"{int((states == '3차 신호 대기').sum())}건",
        "다음 양봉에서 3차 판정",
        False,
    )
    summary["wait2"] = (
        f"{int((states == '2차 신호 대기').sum())}건",
        "1차 신호 후 눌림 대기",
        False,
    )

    if last_scan_time is not None and now is not None:
        last = pd.Timestamp(last_scan_time)
        days = max(0, (pd.Timestamp(now).normalize() - last.normalize()).days)
        value = f"{last:%m/%d %H:%M}"
    elif last_scan_date is None or pd.isna(last_scan_date):
        summary["last"] = ("기록 없음", "통합 스캔을 실행해 주세요", True)
        return summary
    else:
        last = pd.Timestamp(last_scan_date).normalize()
        days = max(0, (pd.Timestamp(today).normalize() - last).days)
        value = f"{last:%m/%d}"
    note = "오늘" if days == 0 else f"{days}일 전"
    stale = days >= 7
    if stale:
        note += " · 스캔 필요"
    summary["last"] = (value, note, stale)
    return summary


def horizon_card_lines(row: pd.Series | None) -> dict[str, tuple[str, str]]:
    """Return (text, tone) for each line of one 3/6/9/12-month card."""
    if row is None:
        return {"win": ("-", ""), "sample": ("", ""), "nearby": ("", ""), "sp500": ("", "")}
    sample = int(row.get("분석 표본", 0) or 0)
    if sample <= 0:
        return {
            "win": ("미산출", ""),
            "sample": ("확정된 매수 없음", ""),
            "nearby": ("", ""),
            "sp500": ("", ""),
        }
    wins = int(row.get("승리", 0) or 0)

    def comparison(label: str, value: object) -> tuple[str, str]:
        if value is None or pd.isna(value):
            return f"{label} 미산출", ""
        tone = "good" if float(value) > 0 else "bad" if float(value) < 0 else ""
        return f"{label} {_format_excess(value)}", tone

    return {
        "win": (f"승률 {float(row['승률']):.1f}%", ""),
        "sample": (f"{sample}건 중 {wins}건 수익", ""),
        "nearby": comparison("평소 매수 대비", row.get("평소 매수 대비 초과")),
        "sp500": comparison("S&P 대비", row.get("S&P 대비 초과")),
    }


def _format_excess(value: object) -> str:
    """Excess return in percentage points, e.g. "+1.23%p"."""
    if value is None or pd.isna(value):
        return "미산출"
    return f"{float(value):+.2f}%p"


def signal_cycles_for_display(data: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "FirstSignalDate": "1차신호일",
        "SecondSignalDate": "2차신호일",
        "ThirdDecisionDate": "3차판정일",
        "Outcome": "결과",
        "Return3M": "3개월후 수익률",
        "Return6M": "6개월후 수익률",
        "Return9M": "9개월후 수익률",
        "Return12M": "12개월후 수익률",
    }
    display = data.rename(columns=rename_map).copy()
    status_columns = {
        "3개월후 수익률": "Return3MStatus",
        "6개월후 수익률": "Return6MStatus",
        "9개월후 수익률": "Return9MStatus",
        "12개월후 수익률": "Return12MStatus",
    }
    for display_column, status_column in status_columns.items():
        if display_column not in display.columns or status_column not in display.columns:
            continue
        display[display_column] = display[display_column].astype(object)
        missing = display[display_column].isna()
        display.loc[missing, display_column] = display.loc[missing, status_column]
    return display.reindex(columns=SIGNAL_HISTORY_DISPLAY_COLUMNS)


def _format_value(value: object, column: str = "") -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if column == MARKET_CAP_RANK_COLUMN and not isinstance(value, str):
        return market_cap_rank_text(value)
    if (
        column.endswith("수익률")
        or column.endswith("손익률")
        or column.endswith("이격률")
        or column in {"승률", "매수 도달률", "중앙값", "최고", "최저"}
    ) and isinstance(
        value, (int, float)
    ):
        return f"{value:+.2f}%"
    if column.endswith("초과") and isinstance(value, (int, float)):
        return _format_excess(value)
    if column == "종합점수" and isinstance(value, (int, float)):
        return f"{value:.2f}"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)
