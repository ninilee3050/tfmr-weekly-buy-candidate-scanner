from __future__ import annotations

import pandas as pd
import pytest

from market_cap_provider import MarketCapCompany
from scanner import scan_trade_cases
from scenario_tracker import (
    ACTIVE_SCENARIO_COLUMNS,
    latest_scan_date,
    load_active_scenarios,
    market_today,
    merge_scan_universe,
    preserve_failed_active_rows,
    save_active_scenarios,
    summarize_ticker_cases,
)
from test_scanner import _case_frame, _week


BASE_WEEK = _week(2)
FRIDAY = pd.Timedelta(days=4)


def company(ticker: str = "TEST", rank: int = 1) -> MarketCapCompany:
    return MarketCapCompany(
        rank=rank,
        ticker=ticker,
        company=f"{ticker} Company",
        market_cap="1.00T",
    )


def summarize(
    data: pd.DataFrame,
    scan_date: pd.Timestamp,
    previous_active: pd.Series | None = None,
    last_scan_date: pd.Timestamp | None = None,
    now: pd.Timestamp | None = None,
):
    cases, buys, full = scan_trade_cases(data, now=now)
    return summarize_ticker_cases(
        company(),
        cases,
        buys,
        full,
        scan_date,
        previous_active=previous_active,
        last_scan_date=last_scan_date,
    )


def tracked(rounds: int, last_checked: pd.Timestamp) -> pd.Series:
    return pd.Series(
        {"티커": "TEST", "1차매수일": BASE_WEEK, "매수차수": rounds, "마지막확인일": last_checked}
    )


def test_active_scenario_state_round_trip(tmp_path) -> None:
    path = tmp_path / "active.csv"
    active = pd.DataFrame(
        [
            {
                "순위": 1,
                "티커": "TEST",
                "회사명": "Test Company",
                "시가총액": "1.00T",
                "현재상태": "보유 중",
                "1차매수일": pd.Timestamp("2024-01-08"),
                "매수차수": 2,
                "평단가": 97.33,
                "마지막확인일": pd.Timestamp("2024-01-12"),
                "데이터기준일": pd.Timestamp("2024-01-08"),
                "데이터상태": "현재 주봉 포함",
            }
        ],
        columns=ACTIVE_SCENARIO_COLUMNS,
    )

    save_active_scenarios(active, path)
    loaded = load_active_scenarios(path)

    assert loaded.loc[0, "티커"] == "TEST"
    assert loaded.loc[0, "1차매수일"] == pd.Timestamp("2024-01-08")
    assert loaded.loc[0, "매수차수"] == 2
    assert loaded.loc[0, "평단가"] == pytest.approx(97.33)
    assert loaded.loc[0, "S&P500 상태"] == "확인불가"


def test_merge_scan_universe_keeps_active_ticker_outside_current_top100() -> None:
    top100 = [company("TOP", rank=1)]
    active = pd.DataFrame(
        [{"순위": 120, "티커": "OLD", "회사명": "Old Company", "시가총액": "10.00B"}]
    )

    merged = merge_scan_universe(top100, active)

    assert [item.ticker for item in merged] == ["TOP", "OLD"]
    assert merged[1].rank == 120


def test_first_buy_this_week_is_reported_and_saved_as_active() -> None:
    data = _case_frame([(105, 100)])

    events, active, closed = summarize(data, BASE_WEEK + FRIDAY)

    assert [(event["단계"], event["결과"], event["신호구분"]) for event in events] == [
        ("1차 매수", "1차 매수", "이번 주")
    ]
    assert events[0]["가격"] == 100
    assert active["현재상태"] == "보유 중"
    assert active["매수차수"] == 1
    assert active["평단가"] == 100
    assert active["다음추가매수가"] == pytest.approx(97.0)
    assert active["마지막확인일"] == BASE_WEEK + FRIDAY
    assert active["데이터상태"] == "현재 주봉 포함"
    assert closed == []


def test_tracked_case_reports_missed_add_on_buy_and_this_weeks_sell() -> None:
    data = _case_frame([(105, 100), (99, 96), (96, 98)], ma5=97, ma20=120)

    events, active, closed = summarize(
        data,
        _week(4) + FRIDAY,
        previous_active=tracked(rounds=1, last_checked=BASE_WEEK + FRIDAY),
    )

    assert [(event["단계"], event["결과"], event["신호구분"]) for event in events] == [
        ("추가매수", "2차 매수", "미확인 기간"),
        ("매도", "매도 완료", "이번 주"),
    ]
    assert active is None
    assert len(closed) == 1
    assert closed[0]["매도일"] == _week(4)
    assert closed[0]["매도가"] == 98
    assert closed[0]["매수차수"] == 2
    assert closed[0]["수익률"] == pytest.approx((98 / ((100 + 96 * 2) / 3) - 1) * 100)
    assert closed[0]["보유주수"] == 2


def test_buys_the_last_scan_saved_are_not_repeated() -> None:
    data = _case_frame([(105, 100), (99, 96), (96.5, 95.5)])

    events, active, _closed = summarize(
        data,
        _week(4) + FRIDAY,
        previous_active=tracked(rounds=2, last_checked=_week(3) + FRIDAY),
    )

    assert events == []
    assert active["매수차수"] == 2


def test_sell_on_the_unfinished_week_is_reported_but_the_case_stays_active() -> None:
    data = _case_frame([(105, 100), (96, 98)], ma5=97, ma20=120)
    wednesday = _week(3) + pd.Timedelta(days=2, hours=12)

    events, active, closed = summarize(
        data,
        wednesday.normalize(),
        previous_active=tracked(rounds=1, last_checked=BASE_WEEK + FRIDAY),
        now=wednesday,
    )

    assert [(event["단계"], event["결과"]) for event in events] == [
        ("매도", "매도 신호 · 잠정")
    ]
    assert events[0]["가격"] == 98
    assert active["현재상태"] == "매도 신호 · 잠정"
    assert closed == []


def test_untracked_ticker_reports_case_that_opened_after_last_scan() -> None:
    data = _case_frame([(105, 100), (99, 96)])

    events, active, _closed = summarize(
        data,
        _week(4) + FRIDAY,
        last_scan_date=_week(1) + FRIDAY,
    )

    assert [event["결과"] for event in events] == ["1차 매수", "2차 매수"]
    assert {event["신호구분"] for event in events} == {"미확인 기간"}
    assert active["매수차수"] == 2


def test_untracked_ticker_does_not_repeat_case_older_than_last_scan() -> None:
    data = _case_frame([(105, 100), (99, 96), (96, 98)], ma5=97, ma20=120)

    events, active, closed = summarize(
        data,
        _week(6) + FRIDAY,
        last_scan_date=_week(5) + FRIDAY,
    )

    assert events == []
    assert active is None
    assert closed == []


def test_failed_active_ticker_is_preserved_for_next_scan() -> None:
    active = pd.DataFrame(
        [
            {
                "순위": 1,
                "티커": "TEST",
                "회사명": "Test Company",
                "시가총액": "1.00T",
                "현재상태": "보유 중",
                "매수차수": 3,
            }
        ],
        columns=ACTIVE_SCENARIO_COLUMNS,
    )

    preserved = preserve_failed_active_rows(active, {"TEST"})

    assert len(preserved) == 1
    assert preserved[0]["매수차수"] == 3
    assert preserved[0]["데이터상태"] == "갱신 실패"


def test_latest_scan_date_uses_most_recent_check() -> None:
    active = pd.DataFrame(
        {
            "티커": ["A", "B", "C"],
            "마지막확인일": [
                pd.Timestamp("2024-01-05"),
                pd.Timestamp("2024-01-12"),
                pd.NaT,
            ],
        }
    )

    assert latest_scan_date(active) == pd.Timestamp("2024-01-12")
    assert latest_scan_date(pd.DataFrame(columns=ACTIVE_SCENARIO_COLUMNS)) is None


def test_market_today_is_naive_normalized_date() -> None:
    today = market_today()

    assert today.tzinfo is None
    assert today == today.normalize()
