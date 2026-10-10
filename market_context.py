from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data_provider import WeeklyDataLoadResult, load_weekly_data_resilient
from indicators import calculate_indicators


SP500_TICKER = "^GSPC"
SP500_NAME = "S&P 500"
SP500_STATUS_COLUMN = "S&P500 상태"
SP500_CACHE_MAX_AGE_SECONDS = 60 * 60


@dataclass(frozen=True)
class Sp500Status:
    display: str
    date: pd.Timestamp | None = None
    close: float | None = None
    ma50: float | None = None

    @property
    def summary(self) -> str:
        if self.date is None or self.close is None or self.ma50 is None:
            return f"S&P500 상태: {self.display}"
        return (
            f"S&P500 상태: {self.display}  |  "
            f"{self.date:%Y-%m-%d} 종가 {self.close:,.2f} · 50주선 {self.ma50:,.2f}"
        )


def load_sp500_context(
    *,
    force_refresh: bool = False,
    expected_latest_date: pd.Timestamp | str | None = None,
    max_cache_age_seconds: float | None = SP500_CACHE_MAX_AGE_SECONDS,
) -> tuple[pd.DataFrame, WeeklyDataLoadResult]:
    """Load one shared S&P 500 weekly series with explicit cache provenance."""
    result = load_weekly_data_resilient(
        SP500_TICKER,
        include_current_week=True,
        force_refresh=force_refresh,
        expected_latest_date=expected_latest_date,
        max_cache_age_seconds=max_cache_age_seconds,
    )
    return calculate_indicators(result.data), result


def sp500_status_at(
    benchmark: pd.DataFrame,
    reference_date: pd.Timestamp | str | None = None,
) -> Sp500Status:
    if benchmark.empty or "Close" not in benchmark.columns or "MA_50" not in benchmark.columns:
        return Sp500Status("확인불가")

    data = benchmark.sort_index()
    if reference_date is not None and not pd.isna(reference_date):
        date = pd.Timestamp(reference_date).normalize()
        data = data.loc[pd.DatetimeIndex(data.index).normalize() <= date]
    if data.empty:
        return Sp500Status("확인불가")

    row = data.iloc[-1]
    actual_date = pd.Timestamp(data.index[-1]).normalize()
    close = pd.to_numeric(pd.Series([row.get("Close")]), errors="coerce").iloc[0]
    ma50 = pd.to_numeric(pd.Series([row.get("MA_50")]), errors="coerce").iloc[0]
    if pd.isna(close) or pd.isna(ma50):
        return Sp500Status("확인불가", date=actual_date)

    display = "50주선 위" if float(close) > float(ma50) else "50주선 아래"
    return Sp500Status(
        display,
        date=actual_date,
        close=float(close),
        ma50=float(ma50),
    )


def annotate_sp500_status(
    data: pd.DataFrame,
    benchmark: pd.DataFrame,
    *,
    reference_date_columns: tuple[str, ...] = (),
    use_latest: bool = False,
    pending_uses_latest: bool = False,
) -> pd.DataFrame:
    """Add a market-regime label without changing any signal or strength score."""
    annotated = data.copy()
    annotated[SP500_STATUS_COLUMN] = "확인불가"

    for index, row in annotated.iterrows():
        result = str(row.get("결과", row.get("현재상태", "")))
        is_pending = "대기" in result
        reference_date: pd.Timestamp | None = None
        if not use_latest and not (pending_uses_latest and is_pending):
            for column in reference_date_columns:
                candidate = pd.to_datetime(row.get(column), errors="coerce")
                if not pd.isna(candidate):
                    reference_date = pd.Timestamp(candidate).normalize()
                    break
        annotated.at[index, SP500_STATUS_COLUMN] = sp500_status_at(
            benchmark,
            reference_date,
        ).display

    return annotated


def sp500_summary_for_cycle(
    benchmark: pd.DataFrame,
    cycle: pd.Series | None,
) -> str:
    if cycle is None:
        return sp500_status_at(benchmark).summary
    outcome = str(cycle.get("Outcome", ""))
    if "대기" in outcome:
        return sp500_status_at(benchmark).summary
    for column in ("ThirdDecisionDate", "SecondSignalDate", "FirstSignalDate"):
        date = pd.to_datetime(cycle.get(column), errors="coerce")
        if not pd.isna(date):
            return sp500_status_at(benchmark, pd.Timestamp(date)).summary
    return sp500_status_at(benchmark).summary
