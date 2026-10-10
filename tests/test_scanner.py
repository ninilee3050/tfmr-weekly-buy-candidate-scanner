from __future__ import annotations

import math

import pandas as pd
import pytest

from scanner import (
    add_buy_base_columns,
    is_cycle_end,
    is_golden_cross,
    scan_trade_cases,
)


def test_ma20_ma50_golden_cross_calculation() -> None:
    previous = pd.Series({"MA_20": 100.0, "MA_50": 100.0})
    current = pd.Series({"MA_20": 101.0, "MA_50": 100.0})
    assert is_golden_cross(previous, current)

    current_equal = pd.Series({"MA_20": 100.0, "MA_50": 100.0})
    assert not is_golden_cross(previous, current_equal)


def test_rising_cycle_end_calculation() -> None:
    previous = pd.Series({"MA_20": 100.0, "MA_50": 100.0})
    current = pd.Series({"MA_20": 99.0, "MA_50": 100.0})
    assert is_cycle_end(previous, current)

    current_equal = pd.Series({"MA_20": 100.0, "MA_50": 100.0})
    assert not is_cycle_end(previous, current_equal)


def test_no_buy_base_without_close_above_ma20_history() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(close=99, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        ]
    )

    assert _base_dates(data) == []


def test_pullback_bullish_candle_is_not_buy_base() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=90, close=95, ma5=96, ma20=100, ma50=99),
        ]
    )

    assert _base_dates(data) == []


def test_first_bearish_candle_later_in_same_pullback_is_buy_base() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=90, close=95, ma5=96, ma20=100, ma50=99),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        ]
    )

    assert _base_dates(data) == [pd.Timestamp("2024-01-22")]


def test_pullback_resets_when_close_recovers_above_ma20_before_bearish_candle() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=90, close=95, ma5=96, ma20=100, ma50=99),
            _row(open_=102, close=103, ma5=101, ma20=100, ma50=99),
        ]
    )

    assert _base_dates(data) == []


def test_ma150_must_be_above_ma200() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99, ma150=10, ma200=10),
        ]
    )

    assert _base_dates(data) == []


def test_only_first_buy_base_is_recorded_in_same_rising_cycle() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
            _row(open_=102, close=103, ma5=101, ma20=100, ma50=99),
            _row(open_=97, close=95, ma5=98, ma20=100, ma50=99),
        ]
    )

    assert _base_dates(data) == [pd.Timestamp("2024-01-15")]


def test_new_golden_cross_after_cycle_end_can_find_new_buy_base() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
            _row(open_=99, close=98, ma5=99, ma20=98, ma50=100),
            _row(open_=103, close=104, ma5=103, ma20=101, ma50=100),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        ]
    )

    assert _base_dates(data) == [
        pd.Timestamp("2024-01-15"),
        pd.Timestamp("2024-02-05"),
    ]


def test_base_candle_below_ma200_is_not_buy_base() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99, ma150=96, ma200=95),
        ]
    )

    assert _base_dates(data) == []


def test_add_on_buys_follow_three_percent_drop_from_last_buy() -> None:
    # Closes of the TSLA case verified in the v3 trade engine.
    data = _case_frame(
        [
            (450.00, 430.41),
            (420.00, 411.11),
            (415.00, 402.51),
            (390.00, 367.96),
            (370.00, 361.83),
            (365.00, 360.59),
            (355.00, 348.95),
        ]
    )

    cases, buys, _full = scan_trade_cases(data)

    assert list(buys["Round"]) == [1, 2, 3, 4]
    assert list(buys["Date"]) == [_week(2), _week(3), _week(5), _week(8)]
    assert list(buys["Quantity"]) == [1, 2, 3, 4]
    assert buys.iloc[1]["DropFromLastBuyPct"] == pytest.approx(-4.484, abs=0.001)
    assert buys.iloc[1]["AveragePrice"] == pytest.approx(417.54, abs=0.01)
    assert buys.iloc[2]["DropFromLastBuyPct"] == pytest.approx(-10.50, abs=0.01)

    case = cases.iloc[0]
    assert len(cases) == 1
    assert case["Outcome"] == "보유 중"
    assert case["BuyRounds"] == 4
    assert case["Quantity"] == 10
    assert case["AveragePrice"] == pytest.approx(375.23, abs=0.01)
    assert case["NextAddBuyPrice"] == pytest.approx(348.95 * 0.97)
    assert case["LastEvent"] == "4차 매수"


def test_drop_just_short_of_three_percent_does_not_add() -> None:
    data = _case_frame([(105, 100), (100, 97.01)])

    _cases, buys, _full = scan_trade_cases(data)

    assert list(buys["Round"]) == [1]


def test_bullish_week_never_adds_even_after_a_large_drop() -> None:
    data = _case_frame([(105, 100), (80, 90)], ma5=95, ma20=120)

    cases, buys, _full = scan_trade_cases(data)

    assert list(buys["Round"]) == [1]
    assert cases.iloc[0]["Outcome"] == "보유 중"


def test_buy_rounds_stop_at_five() -> None:
    data = _case_frame([(105, 100), (99, 96), (95, 92), (91, 88), (87, 84), (83, 80)])

    cases, buys, _full = scan_trade_cases(data)

    assert list(buys["Round"]) == [1, 2, 3, 4, 5]
    assert cases.iloc[0]["Quantity"] == 15
    assert math.isnan(cases.iloc[0]["NextAddBuyPrice"])


def test_first_bullish_week_above_ma5_sells_everything() -> None:
    data = _case_frame([(105, 100), (99, 96), (96, 98)], ma5=97, ma20=120)

    cases, _buys, full = scan_trade_cases(data)

    case = cases.iloc[0]
    assert case["Outcome"] == "매도 완료"
    assert case["SellDate"] == _week(4)
    assert case["SellPrice"] == 98
    assert case["AveragePrice"] == pytest.approx((100 + 96 * 2) / 3)
    assert case["ReturnPct"] == pytest.approx((98 / ((100 + 96 * 2) / 3) - 1) * 100)
    assert case["HoldingWeeks"] == 2
    assert bool(full.loc[_week(4), "tfmr_sell"])
    assert not bool(full.loc[_week(4), "tfmr_holding"])


def test_bullish_week_above_ma20_only_also_sells() -> None:
    data = _case_frame([(105, 100), (96, 98)], ma5=99, ma20=97)

    cases, _buys, _full = scan_trade_cases(data)

    assert cases.iloc[0]["Outcome"] == "매도 완료"


def test_bullish_week_below_both_averages_keeps_holding() -> None:
    data = _case_frame([(105, 100), (96, 98)], ma5=99, ma20=120)

    cases, _buys, _full = scan_trade_cases(data)

    assert cases.iloc[0]["Outcome"] == "보유 중"
    assert cases.iloc[0]["ReturnPct"] == pytest.approx(-2.0)


def test_sell_on_unfinished_week_stays_open_and_provisional() -> None:
    data = _case_frame([(105, 100), (96, 98)], ma5=97, ma20=120)

    cases, _buys, _full = scan_trade_cases(data, now=pd.Timestamp("2024-01-23 12:00"))

    case = cases.iloc[0]
    assert case["Outcome"] == "보유 중"
    assert case["LastEvent"] == "매도"
    assert bool(case["Provisional"])
    assert pd.isna(case["SellDate"])


def test_buy_on_unfinished_week_is_provisional() -> None:
    data = _case_frame([(105, 100)])

    cases, _buys, _full = scan_trade_cases(data, now=pd.Timestamp("2024-01-16 12:00"))

    assert cases.iloc[0]["LastEvent"] == "1차 매수"
    assert bool(cases.iloc[0]["Provisional"])


def test_new_cycle_after_sell_opens_second_case() -> None:
    rows = [
        _row(close=99, ma20=100, ma50=101),
        _row(open_=104, close=105, ma20=102, ma50=101),
        _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        _row(open_=97, close=98, ma5=97, ma20=98, ma50=100),
        _row(open_=103, close=104, ma5=103, ma20=101, ma50=100),
        _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
    ]

    cases, _buys, _full = scan_trade_cases(_frame(rows))

    assert list(cases["Outcome"]) == ["매도 완료", "보유 중"]
    assert list(cases["FirstBuyDate"]) == [_week(2), _week(5)]


def test_base_candle_while_holding_does_not_open_second_case() -> None:
    rows = [
        _row(close=99, ma20=100, ma50=101),
        _row(open_=104, close=105, ma20=102, ma50=101),
        _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        _row(open_=95, close=93.5, ma5=96, ma20=98, ma50=100),
        _row(open_=95, close=94, ma5=95, ma20=93, ma50=92),
        _row(open_=93.5, close=92.5, ma5=94, ma20=93, ma50=92),
    ]

    cases, buys, full = scan_trade_cases(_frame(rows))

    assert bool(full.loc[_week(5), "tfmr_buy_base"])
    assert len(cases) == 1
    assert list(buys["Round"]) == [1]


def test_first_pullback_of_a_cycle_is_pullback_number_one() -> None:
    cases, _buys, _full = scan_trade_cases(_case_frame([(105, 100)]))

    assert cases.iloc[0]["PullbackNumber"] == 1


def test_base_candle_after_a_skipped_pullback_is_pullback_number_two() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            # First pullback of the cycle, below MA200: counted but not bought.
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99, ma150=96, ma200=95),
            _row(open_=95, close=93, ma5=96, ma20=100, ma50=99, ma150=96, ma200=95),
            _row(open_=100, close=103, ma5=101, ma20=100, ma50=99),
            _row(open_=97, close=95, ma5=98, ma20=100, ma50=99),
        ]
    )

    cases, _buys, full = scan_trade_cases(data)

    assert list(full["tfmr_pullback_number"]) == [0, 0, 1, 1, 1, 2]
    assert list(cases["FirstBuyDate"]) == [_week(5)]
    assert cases.iloc[0]["PullbackNumber"] == 2
    assert cases.iloc[0]["BuyRounds"] == 1


def test_pullback_count_restarts_with_a_new_golden_cross() -> None:
    rows = [
        _row(close=99, ma20=100, ma50=101),
        _row(open_=104, close=105, ma20=102, ma50=101),
        _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        _row(open_=97, close=98, ma5=97, ma20=98, ma50=100),
        _row(open_=103, close=104, ma5=103, ma20=101, ma50=100),
        _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
    ]

    cases, _buys, _full = scan_trade_cases(_frame(rows))

    assert list(cases["PullbackNumber"]) == [1, 1]


def _base_dates(data: pd.DataFrame) -> list[pd.Timestamp]:
    full = add_buy_base_columns(data)
    return list(full.index[full["tfmr_buy_base"]])


def _case_frame(
    candles: list[tuple[float, float]],
    ma5: float = 1000,
    ma20: float = 1000,
) -> pd.DataFrame:
    """Two set-up weeks, a base candle from the first tuple, then the rest."""
    first_open, first_close = candles[0]
    rows = [
        _row(close=first_close + 5, ma20=first_close + 6, ma50=first_close + 7),
        _row(
            open_=first_close + 9,
            close=first_close + 10,
            ma20=first_close + 8,
            ma50=first_close + 7,
        ),
        _row(
            open_=first_open,
            close=first_close,
            ma5=first_close + 3,
            ma20=first_close + 6,
            ma50=first_close + 5,
        ),
    ]
    rows.extend(
        _row(open_=open_, close=close, ma5=ma5, ma20=ma20, ma50=ma20 - 1)
        for open_, close in candles[1:]
    )
    return _frame(rows)


def _week(position: int) -> pd.Timestamp:
    return pd.Timestamp("2024-01-01") + pd.Timedelta(weeks=position)


def _frame(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=pd.date_range("2024-01-01", periods=len(rows), freq="W-MON"))


def _row(
    open_: float = 100,
    close: float = 100,
    ma5: float = 101,
    ma20: float = 100,
    ma50: float = 100,
    ma150: float = 20,
    ma200: float = 10,
) -> dict[str, float]:
    return {
        "Open": open_,
        "Close": close,
        "MA_5": ma5,
        "MA_20": ma20,
        "MA_50": ma50,
        "MA_150": ma150,
        "MA_200": ma200,
    }
