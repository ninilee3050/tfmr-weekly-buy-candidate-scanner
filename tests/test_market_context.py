from __future__ import annotations

import pandas as pd

from market_context import (
    SP500_STATUS_COLUMN,
    annotate_sp500_status,
    sp500_status_at,
)


def benchmark_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Close": [90.0, 105.0, 95.0],
            "MA_50": [100.0, 100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"]),
    )


def test_sp500_status_uses_last_week_available_at_reference_date() -> None:
    data = benchmark_frame()

    below = sp500_status_at(data, "2024-01-03")
    above = sp500_status_at(data, "2024-01-12")

    assert below.display == "50주선 아래"
    assert below.date == pd.Timestamp("2024-01-01")
    assert above.display == "50주선 위"
    assert above.date == pd.Timestamp("2024-01-08")


def test_market_status_uses_the_sell_week_and_the_latest_week_for_held_cases() -> None:
    cases = pd.DataFrame(
        [
            {"결과": "매도 완료", "매도일": "2024-01-08"},
            {"결과": "보유 중", "매도일": pd.NaT},
        ]
    )

    result = annotate_sp500_status(
        cases,
        benchmark_frame(),
        reference_date_columns=("매도일",),
    )

    assert result.loc[0, SP500_STATUS_COLUMN] == "50주선 위"
    assert result.loc[1, SP500_STATUS_COLUMN] == "50주선 아래"


def test_status_summary_contains_market_values() -> None:
    summary = sp500_status_at(benchmark_frame(), pd.Timestamp("2024-01-08")).summary

    assert "S&P500 상태: 50주선 위" in summary
    assert "2024-01-08" in summary
    assert "종가 105.00" in summary
