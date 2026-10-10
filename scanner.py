from __future__ import annotations

import pandas as pd

from data_provider import weekly_bar_in_progress


ADD_BUY_DROP_RATIO = 0.03
MAX_BUY_ROUNDS = 5
OUTCOME_HOLDING = "보유 중"
OUTCOME_SOLD = "매도 완료"
SELL_EVENT = "매도"

REQUIRED_COLUMNS = ("Open", "Close", "MA_5", "MA_20", "MA_50", "MA_150", "MA_200")

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


def buy_round_label(buy_round: object) -> str:
    return f"{int(buy_round)}차 매수"


def add_buy_base_columns(data: pd.DataFrame) -> pd.DataFrame:
    """Mark the first buy base candle of each MA20/MA50 rising cycle.

    A rising cycle starts when MA20 crosses above MA50 and ends when it
    crosses back below.  Once a week in the cycle has closed above MA20, the
    first bearish week that closes below both MA5 and MA20 while MA150 > MA200
    and Close > MA200 is the base candle.  A cycle yields one base candle.
    """
    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing)}")

    full = data.sort_index().copy()
    for column in (
        "tfmr_golden_cross",
        "tfmr_cycle_end",
        "tfmr_in_rising_cycle",
        "tfmr_buy_base",
    ):
        full[column] = False

    in_cycle = False
    close_above_ma20_seen = False
    buy_recorded_in_cycle = False
    previous: pd.Series | None = None

    for date, row in full.iterrows():
        golden_cross = previous is not None and is_golden_cross(previous, row)
        cycle_end = previous is not None and is_cycle_end(previous, row)

        if cycle_end:
            in_cycle = False
        if golden_cross:
            in_cycle = True
        if cycle_end or golden_cross:
            close_above_ma20_seen = False
            buy_recorded_in_cycle = False

        if in_cycle:
            if _above(row, "Close", "MA_20"):
                close_above_ma20_seen = True
            elif (
                close_above_ma20_seen
                and not buy_recorded_in_cycle
                and _is_pullback(row)
                and _is_bearish(row)
                and _long_trend_ok(row)
            ):
                buy_recorded_in_cycle = True
                full.at[date, "tfmr_buy_base"] = True

        full.at[date, "tfmr_golden_cross"] = golden_cross
        full.at[date, "tfmr_cycle_end"] = cycle_end
        full.at[date, "tfmr_in_rising_cycle"] = in_cycle
        previous = row

    return full


def scan_trade_cases(
    data: pd.DataFrame,
    now: pd.Timestamp | None = None,
    weekend_traded: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Follow every first buy base candle through add-on buys to the sell week.

    A case opens on a base candle (1 share at the weekly close).  While it is
    open, a bearish week closing 3% or more below the last buy price adds the
    next round (round N buys N shares, up to round 5); otherwise the first
    bullish week closing above MA5 or MA20 sells everything.  A base candle
    that appears while a case is still open does not open a second case.

    A sell seen on the unfinished current week is not final: the case stays
    open and is flagged ``Provisional``, as is any buy on that week.

    Returns the cases, every buy of every case, and the annotated weekly table.
    """
    full = add_buy_base_columns(data)
    full["tfmr_buy_round"] = 0
    full["tfmr_sell"] = False
    full["tfmr_holding"] = False

    in_progress_date = (
        full.index[-1]
        if len(full)
        and weekly_bar_in_progress(full.index[-1], now=now, weekend_traded=weekend_traded)
        else None
    )
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
                case["LastEvent"] = SELL_EVENT
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


def is_golden_cross(previous: pd.Series, current: pd.Series) -> bool:
    if _has_missing(previous, current):
        return False
    return previous["MA_20"] <= previous["MA_50"] and current["MA_20"] > current["MA_50"]


def is_cycle_end(previous: pd.Series, current: pd.Series) -> bool:
    if _has_missing(previous, current):
        return False
    return previous["MA_20"] >= previous["MA_50"] and current["MA_20"] < current["MA_50"]


def _has_missing(previous: pd.Series, current: pd.Series) -> bool:
    return any(
        pd.isna(row.get(column))
        for row in (previous, current)
        for column in ("MA_20", "MA_50")
    )


def _above(row: pd.Series, column: str, reference: str) -> bool:
    """Strictly above; a missing value is never above or below anything."""
    if pd.isna(row.get(column)) or pd.isna(row.get(reference)):
        return False
    return bool(row[column] > row[reference])


def _is_pullback(row: pd.Series) -> bool:
    return _above(row, "MA_5", "Close") and _above(row, "MA_20", "Close")


def _is_bearish(row: pd.Series) -> bool:
    return _above(row, "Open", "Close")


def _is_bullish(row: pd.Series) -> bool:
    return _above(row, "Close", "Open")


def _long_trend_ok(row: pd.Series) -> bool:
    return _above(row, "MA_150", "MA_200") and _above(row, "Close", "MA_200")


def _is_add_buy(case: dict[str, object], row: pd.Series) -> bool:
    if case["BuyRounds"] >= MAX_BUY_ROUNDS or not _is_bearish(row):
        return False
    return row["Close"] / case["LastBuyPrice"] - 1 <= -ADD_BUY_DROP_RATIO


def _is_sell(row: pd.Series) -> bool:
    return _is_bullish(row) and (
        _above(row, "Close", "MA_5") or _above(row, "Close", "MA_20")
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
    case["LastEvent"] = buy_round_label(buy_round)
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
            "LastEvent": SELL_EVENT,
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
