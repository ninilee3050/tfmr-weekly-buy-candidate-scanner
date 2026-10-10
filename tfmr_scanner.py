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
    "Close<MA5/MA20 + 음봉 + MA150>MA200 + Close>MA200"
)
ADD_BUY_DROP_RATIO = 0.03
MAX_BUY_ROUNDS = 5
OUTCOME_HOLDING = "보유 중"
OUTCOME_SOLD = "매도 완료"
TRADE_CASE_COLUMNS = [
    "FirstBuyDate",
    "BuyRounds",
    "LastBuyDate",
    "LastBuyPrice",
    "Quantity",
    "AveragePrice",
    "NextAddBuyPrice",
    "SellDate",
    "SellPrice",
    "Outcome",
    "ReturnPct",
    "HoldingWeeks",
    "LastEvent",
    "LastEventDate",
    "Provisional",
]
TRADE_BUY_COLUMNS = [
    "FirstBuyDate",
    "Round",
    "Date",
    "Price",
    "Quantity",
    "DropFromLastBuyPct",
    "HoldingQuantity",
    "AveragePrice",
]


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


def scan_trade_cases(
    data: pd.DataFrame,
    last_bar_in_progress: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Follow every first buy base candle through add-on buys to the sell week.

    A case opens on a first buy base candle (1 share at the weekly close).  While
    it is open, a bearish week closing 3% or more below the last buy price adds
    the next round (round N buys N shares, up to round 5); otherwise the first
    bullish week closing above MA5 or MA20 sells everything.  A base candle that
    appears while a case is still open does not open a second case.

    A sell seen on the unfinished current week is not final: the case stays
    open and is flagged ``Provisional``, as is any buy on that week.
    """
    _buy_points, full = scan_tfmr_buy_points(data)
    full["tfmr_buy_round"] = 0
    full["tfmr_sell"] = False
    full["tfmr_holding"] = False

    in_progress_date = full.index[-1] if last_bar_in_progress and len(full) else None
    case_rows: list[dict[str, object]] = []
    buy_rows: list[dict[str, object]] = []
    case: dict[str, object] | None = None

    for position, (date, row) in enumerate(full.iterrows()):
        provisional = in_progress_date is not None and date == in_progress_date

        if case is None:
            if bool(row["tfmr_buy_base"]):
                case = _open_case(date, position)
                _record_buy(case, buy_rows, date, row["Close"], provisional)
                full.at[date, "tfmr_buy_round"] = 1
                full.at[date, "tfmr_holding"] = True
            continue

        if _is_add_buy(case, row):
            _record_buy(case, buy_rows, date, row["Close"], provisional)
            full.at[date, "tfmr_buy_round"] = case["BuyRounds"]
        elif _is_sell(row):
            full.at[date, "tfmr_sell"] = True
            if provisional:
                case["LastEvent"] = "매도"
                case["LastEventDate"] = pd.Timestamp(date).normalize()
                case["Provisional"] = True
            else:
                case_rows.append(_closed_case_row(case, date, position, row["Close"]))
                case = None
                continue
        full.at[date, "tfmr_holding"] = True

    if case is not None:
        case_rows.append(_open_case_row(case, full))

    cases = pd.DataFrame(case_rows, columns=TRADE_CASE_COLUMNS)
    buys = pd.DataFrame(buy_rows, columns=TRADE_BUY_COLUMNS)
    return cases, buys, full


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
    for column in ("Close", "MA150", "MA200"):
        if pd.isna(row.get(column)):
            return False
    return row["MA150"] > row["MA200"] and row["Close"] > row["MA200"]


def _is_bullish(row: pd.Series) -> bool:
    if pd.isna(row.get("Open")) or pd.isna(row.get("Close")):
        return False
    return row["Close"] > row["Open"]


def _is_add_buy(case: dict[str, object], row: pd.Series) -> bool:
    if case["BuyRounds"] >= MAX_BUY_ROUNDS or not _is_bearish(row):
        return False
    return row["Close"] / case["LastBuyPrice"] - 1 <= -ADD_BUY_DROP_RATIO


def _is_sell(row: pd.Series) -> bool:
    if not _is_bullish(row):
        return False
    return any(
        not pd.isna(row.get(column)) and row["Close"] > row[column]
        for column in ("MA5", "MA20")
    )


def _open_case(date: pd.Timestamp, position: int) -> dict[str, object]:
    return {
        "FirstBuyDate": pd.Timestamp(date).normalize(),
        "FirstBuyPosition": position,
        "BuyRounds": 0,
        "LastBuyDate": pd.NaT,
        "LastBuyPrice": float("nan"),
        "Quantity": 0,
        "Cost": 0.0,
        "LastEvent": "",
        "LastEventDate": pd.NaT,
        "Provisional": False,
    }


def _record_buy(
    case: dict[str, object],
    buy_rows: list[dict[str, object]],
    date: pd.Timestamp,
    price: float,
    provisional: bool,
) -> None:
    date = pd.Timestamp(date).normalize()
    buy_round = case["BuyRounds"] + 1
    drop = (
        float("nan")
        if buy_round == 1
        else (price / case["LastBuyPrice"] - 1) * 100
    )
    case["BuyRounds"] = buy_round
    case["Quantity"] += buy_round
    case["Cost"] += price * buy_round
    case["LastBuyDate"] = date
    case["LastBuyPrice"] = price
    case["LastEvent"] = f"{buy_round}차 매수"
    case["LastEventDate"] = date
    case["Provisional"] = provisional
    buy_rows.append(
        {
            "FirstBuyDate": case["FirstBuyDate"],
            "Round": buy_round,
            "Date": date,
            "Price": price,
            "Quantity": buy_round,
            "DropFromLastBuyPct": drop,
            "HoldingQuantity": case["Quantity"],
            "AveragePrice": case["Cost"] / case["Quantity"],
        }
    )


def _case_row(case: dict[str, object]) -> dict[str, object]:
    row = {column: case.get(column) for column in TRADE_CASE_COLUMNS}
    row["AveragePrice"] = case["Cost"] / case["Quantity"]
    return row


def _closed_case_row(
    case: dict[str, object],
    date: pd.Timestamp,
    position: int,
    price: float,
) -> dict[str, object]:
    date = pd.Timestamp(date).normalize()
    row = _case_row(case)
    row.update(
        {
            "NextAddBuyPrice": float("nan"),
            "SellDate": date,
            "SellPrice": price,
            "Outcome": OUTCOME_SOLD,
            "ReturnPct": (price / row["AveragePrice"] - 1) * 100,
            "HoldingWeeks": position - case["FirstBuyPosition"],
            "LastEvent": "매도",
            "LastEventDate": date,
            "Provisional": False,
        }
    )
    return row


def _open_case_row(case: dict[str, object], full: pd.DataFrame) -> dict[str, object]:
    row = _case_row(case)
    last_close = full.iloc[-1]["Close"]
    row.update(
        {
            "NextAddBuyPrice": (
                case["LastBuyPrice"] * (1 - ADD_BUY_DROP_RATIO)
                if case["BuyRounds"] < MAX_BUY_ROUNDS
                else float("nan")
            ),
            "SellDate": pd.NaT,
            "SellPrice": float("nan"),
            "Outcome": OUTCOME_HOLDING,
            "ReturnPct": (last_close / row["AveragePrice"] - 1) * 100,
            "HoldingWeeks": len(full) - 1 - case["FirstBuyPosition"],
        }
    )
    return row


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
