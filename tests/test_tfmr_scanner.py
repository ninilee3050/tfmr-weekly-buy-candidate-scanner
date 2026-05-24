from __future__ import annotations

import pandas as pd

from tfmr_scanner import (
    calculate_moving_averages,
    is_cycle_end,
    is_golden_cross,
    scan_tfmr_buy_points,
)


def test_ma20_ma50_golden_cross_calculation() -> None:
    previous = pd.Series({"MA20": 100.0, "MA50": 100.0})
    current = pd.Series({"MA20": 101.0, "MA50": 100.0})
    assert is_golden_cross(previous, current)

    current_equal = pd.Series({"MA20": 100.0, "MA50": 100.0})
    assert not is_golden_cross(previous, current_equal)


def test_rising_cycle_end_calculation() -> None:
    previous = pd.Series({"MA20": 100.0, "MA50": 100.0})
    current = pd.Series({"MA20": 99.0, "MA50": 100.0})
    assert is_cycle_end(previous, current)

    current_equal = pd.Series({"MA20": 100.0, "MA50": 100.0})
    assert not is_cycle_end(previous, current_equal)


def test_no_buy_base_without_close_above_ma20_history() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(close=99, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        ]
    )

    buy_points, _full = scan_tfmr_buy_points(data)

    assert buy_points.empty


def test_pullback_bullish_candle_is_not_buy_base() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=90, close=95, ma5=96, ma20=100, ma50=99),
        ]
    )

    buy_points, _full = scan_tfmr_buy_points(data)

    assert buy_points.empty


def test_first_bearish_candle_later_in_same_pullback_is_buy_base() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=90, close=95, ma5=96, ma20=100, ma50=99),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        ]
    )

    buy_points, _full = scan_tfmr_buy_points(data)

    assert list(buy_points.index) == [pd.Timestamp("2024-01-22")]


def test_pullback_resets_when_close_recovers_above_ma20_before_bearish_candle() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=90, close=95, ma5=96, ma20=100, ma50=99),
            _row(open_=102, close=103, ma5=101, ma20=100, ma50=99),
        ]
    )

    buy_points, full = scan_tfmr_buy_points(data)

    assert buy_points.empty
    assert not bool(full.loc[pd.Timestamp("2024-01-22"), "tfmr_pullback_active"])


def test_ma150_must_be_above_ma200() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99, ma150=100, ma200=100),
        ]
    )

    buy_points, _full = scan_tfmr_buy_points(data)

    assert buy_points.empty


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

    buy_points, _full = scan_tfmr_buy_points(data)

    assert list(buy_points.index) == [pd.Timestamp("2024-01-15")]


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

    buy_points, _full = scan_tfmr_buy_points(data)

    assert list(buy_points.index) == [
        pd.Timestamp("2024-01-15"),
        pd.Timestamp("2024-02-05"),
    ]


def test_calculate_moving_averages_uses_weekly_close_sma() -> None:
    data = pd.DataFrame(
        {"Open": [1, 2, 3, 4, 5], "Close": [10, 20, 30, 40, 50]},
        index=pd.date_range("2024-01-01", periods=5, freq="W-MON"),
    )

    result = calculate_moving_averages(data)

    assert pd.isna(result.iloc[3]["MA5"])
    assert result.iloc[4]["MA5"] == 30


def _frame(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=pd.date_range("2024-01-01", periods=len(rows), freq="W-MON"))


def _row(
    open_: float = 100,
    close: float = 100,
    ma5: float = 101,
    ma20: float = 100,
    ma50: float = 100,
    ma150: float = 120,
    ma200: float = 100,
) -> dict[str, float]:
    return {
        "Open": open_,
        "Close": close,
        "MA5": ma5,
        "MA20": ma20,
        "MA50": ma50,
        "MA150": ma150,
        "MA200": ma200,
    }
