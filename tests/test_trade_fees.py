from __future__ import annotations

import pytest

from scanner import scan_trade_cases
from test_scanner import _case_frame
from trade_fees import DEFAULT_FEES, NO_FEES, FeeSchedule


def test_default_fees_take_about_a_fifth_of_a_percent_from_a_round_trip() -> None:
    # Bought for 100, sold for 100: only the costs remain.
    assert DEFAULT_FEES.net_return_pct(100.0, 100.0, 1) == pytest.approx(-0.2021, abs=0.0005)


def test_buy_fee_raises_the_cost_and_sell_fees_cut_the_proceeds() -> None:
    fees = FeeSchedule(buy_rate=0.01, sell_rate=0.02, sec_rate=0.001, taf_per_share=0.5)

    assert fees.buy_cost(200.0) == pytest.approx(202.0)
    assert fees.sell_proceeds(300.0, 4) == pytest.approx(300.0 * (1 - 0.021) - 2.0)
    assert fees.net_return_pct(200.0, 300.0, 4) == pytest.approx((291.7 / 202.0 - 1) * 100)


def test_no_fees_gives_the_plain_return() -> None:
    assert NO_FEES.net_return_pct(94.0, 98.0, 1) == pytest.approx((98 / 94 - 1) * 100)


def test_sold_case_has_a_net_return_below_its_gross_return() -> None:
    data = _case_frame([(105, 100), (99, 96), (96, 98)], ma5=97, ma20=120)

    case = scan_trade_cases(data)[0].iloc[0]
    without_fees = scan_trade_cases(data, fees=NO_FEES)[0].iloc[0]

    cost, proceeds = 100 + 96 * 2, 98 * 3
    assert case["ReturnPct"] == pytest.approx((proceeds / cost - 1) * 100)
    assert case["NetReturnPct"] == pytest.approx(DEFAULT_FEES.net_return_pct(cost, proceeds, 3))
    assert 0 < case["ReturnPct"] - case["NetReturnPct"] < 0.25
    assert without_fees["NetReturnPct"] == pytest.approx(without_fees["ReturnPct"])


def test_small_gain_turns_into_a_loss_after_fees() -> None:
    data = _case_frame([(100.5, 100), (99.9, 100.1)], ma5=100.05, ma20=120)

    case = scan_trade_cases(data)[0].iloc[0]

    assert case["Outcome"] == "매도 완료"
    assert case["ReturnPct"] == pytest.approx(0.1)
    assert case["NetReturnPct"] < 0


def test_held_case_shows_the_net_return_of_selling_at_the_latest_close() -> None:
    data = _case_frame([(105, 100), (99, 98.5)])

    case = scan_trade_cases(data)[0].iloc[0]

    assert case["Outcome"] == "보유 중"
    assert case["NetReturnPct"] == pytest.approx(DEFAULT_FEES.net_return_pct(100, 98.5, 1))
