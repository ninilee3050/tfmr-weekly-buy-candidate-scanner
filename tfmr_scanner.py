from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


MA_PERIODS = (5, 20, 50, 150, 200)
MA_COLUMNS = [f"MA{period}" for period in MA_PERIODS]
BUY_POINT_COLUMNS = [
    "Open",
    "Close",
    "MA5",
    "MA20",
    "MA50",
    "MA150",
    "MA200",
    "ConditionSummary",
]
CONDITION_SUMMARY = (
    "1회차 기준봉: MA20>MA50 상승사이클 + Close>MA20 이력 + "
    "Close<MA5/MA20 + 음봉 + MA150>MA200"
)


def calculate_moving_averages(data: pd.DataFrame) -> pd.DataFrame:
    """Add weekly close-based SMA columns used by TFMR v1."""
    if "Close" not in data.columns:
        raise ValueError("Close 컬럼이 필요합니다.")

    result = data.copy().sort_index()
    for period in MA_PERIODS:
        column = f"MA{period}"
        result[column] = result["Close"].rolling(window=period, min_periods=period).mean()
    return result


def ensure_moving_averages(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy().sort_index()
    missing = [column for column in MA_COLUMNS if column not in result.columns]
    if missing:
        calculated = calculate_moving_averages(result)
        for column in missing:
            result[column] = calculated[column]
    return result


def is_golden_cross(previous: pd.Series, current: pd.Series) -> bool:
    if _has_missing(previous, current, ("MA20", "MA50")):
        return False
    return previous["MA20"] <= previous["MA50"] and current["MA20"] > current["MA50"]


def is_cycle_end(previous: pd.Series, current: pd.Series) -> bool:
    if _has_missing(previous, current, ("MA20", "MA50")):
        return False
    return previous["MA20"] >= previous["MA50"] and current["MA20"] < current["MA50"]


def scan_tfmr_buy_points(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Track TFMR v1 state from the beginning and return first buy base candles.

    The function does not trade. It only identifies the first bearish pullback
    candle after a MA20/MA50 rising cycle has started and Close>MA20 history
    exists in that cycle.
    """
    _validate_input(data)
    full = ensure_moving_averages(data)
    full = _add_state_columns(full)

    in_cycle = False
    close_above_ma20_seen = False
    pullback_active = False
    buy_recorded_in_cycle = False
    previous: pd.Series | None = None
    buy_rows: list[dict[str, object]] = []

    for date, row in full.iterrows():
        golden_cross = previous is not None and is_golden_cross(previous, row)
        cycle_end = previous is not None and is_cycle_end(previous, row)
        buy_base = False

        if cycle_end:
            in_cycle = False
            close_above_ma20_seen = False
            pullback_active = False
            buy_recorded_in_cycle = False

        if golden_cross:
            in_cycle = True
            close_above_ma20_seen = False
            pullback_active = False
            buy_recorded_in_cycle = False

        if in_cycle:
            if _close_above_ma20(row):
                close_above_ma20_seen = True
                pullback_active = False
            elif (
                close_above_ma20_seen
                and not buy_recorded_in_cycle
                and _is_pullback(row)
            ):
                pullback_active = True
                if _is_bearish(row) and _long_trend_ok(row):
                    buy_base = True
                    buy_recorded_in_cycle = True
                    pullback_active = False
                    buy_rows.append(_buy_point_row(date, row))

        full.at[date, "tfmr_golden_cross"] = golden_cross
        full.at[date, "tfmr_cycle_end"] = cycle_end
        full.at[date, "tfmr_in_rising_cycle"] = in_cycle
        full.at[date, "tfmr_close_above_ma20_seen"] = close_above_ma20_seen
        full.at[date, "tfmr_pullback_active"] = pullback_active
        full.at[date, "tfmr_buy_recorded_in_cycle"] = buy_recorded_in_cycle
        full.at[date, "tfmr_buy_base"] = buy_base

        previous = row

    buy_points = _buy_points_frame(buy_rows)
    return buy_points, full


def current_week_buy_point(
    buy_points: pd.DataFrame,
    scan_date: pd.Timestamp | str | None = None,
) -> pd.Series | None:
    week_start = monday_week_start(scan_date)
    if buy_points.empty:
        return None

    index = pd.DatetimeIndex(buy_points.index).normalize()
    matches = buy_points.loc[index == week_start]
    if matches.empty:
        return None
    return matches.iloc[0]


def monday_week_start(date: pd.Timestamp | str | None = None) -> pd.Timestamp:
    value = pd.Timestamp.today() if date is None else pd.Timestamp(date)
    normalized = value.normalize()
    return normalized - pd.Timedelta(days=normalized.weekday())


def _validate_input(data: pd.DataFrame) -> None:
    missing = [column for column in ("Open", "Close") if column not in data.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")


def _add_state_columns(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    for column in (
        "tfmr_golden_cross",
        "tfmr_cycle_end",
        "tfmr_in_rising_cycle",
        "tfmr_close_above_ma20_seen",
        "tfmr_pullback_active",
        "tfmr_buy_recorded_in_cycle",
        "tfmr_buy_base",
    ):
        result[column] = False
    return result


def _has_missing(previous: pd.Series, current: pd.Series, columns: Iterable[str]) -> bool:
    for column in columns:
        if pd.isna(previous.get(column)) or pd.isna(current.get(column)):
            return True
    return False


def _close_above_ma20(row: pd.Series) -> bool:
    if pd.isna(row.get("Close")) or pd.isna(row.get("MA20")):
        return False
    return row["Close"] > row["MA20"]


def _is_pullback(row: pd.Series) -> bool:
    for column in ("Close", "MA5", "MA20"):
        if pd.isna(row.get(column)):
            return False
    return row["Close"] < row["MA5"] and row["Close"] < row["MA20"]


def _is_bearish(row: pd.Series) -> bool:
    if pd.isna(row.get("Open")) or pd.isna(row.get("Close")):
        return False
    return row["Close"] < row["Open"]


def _long_trend_ok(row: pd.Series) -> bool:
    if pd.isna(row.get("MA150")) or pd.isna(row.get("MA200")):
        return False
    return row["MA150"] > row["MA200"]


def _buy_point_row(date: pd.Timestamp, row: pd.Series) -> dict[str, object]:
    return {
        "Date": pd.Timestamp(date).normalize(),
        "Open": row["Open"],
        "Close": row["Close"],
        "MA5": row["MA5"],
        "MA20": row["MA20"],
        "MA50": row["MA50"],
        "MA150": row["MA150"],
        "MA200": row["MA200"],
        "ConditionSummary": CONDITION_SUMMARY,
    }


def _buy_points_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        empty = pd.DataFrame(columns=BUY_POINT_COLUMNS)
        empty.index.name = "Date"
        return empty

    frame = pd.DataFrame(rows).set_index("Date")
    frame.index = pd.DatetimeIndex(frame.index)
    frame.index.name = "Date"
    return frame[BUY_POINT_COLUMNS]
