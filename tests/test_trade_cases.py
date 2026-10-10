from __future__ import annotations

import math

import pandas as pd
import pytest

from tfmr_scanner import scan_tfmr_buy_points, scan_trade_cases


def test_base_candle_below_ma200_is_not_buy_base() -> None:
    data = _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99, ma150=96, ma200=95),
        ]
    )

    buy_points, _full = scan_tfmr_buy_points(data)

    assert buy_points.empty


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

    cases, _buys, _full = scan_trade_cases(data, last_bar_in_progress=True)

    case = cases.iloc[0]
    assert case["Outcome"] == "보유 중"
    assert case["LastEvent"] == "매도"
    assert bool(case["Provisional"])
    assert pd.isna(case["SellDate"])


def test_buy_on_unfinished_week_is_provisional() -> None:
    data = _case_frame([(105, 100)])

    cases, _buys, _full = scan_trade_cases(data, last_bar_in_progress=True)

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
        "MA5": ma5,
        "MA20": ma20,
        "MA50": ma50,
        "MA150": ma150,
        "MA200": ma200,
    }
