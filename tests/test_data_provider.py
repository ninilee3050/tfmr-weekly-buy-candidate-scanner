from __future__ import annotations

import pandas as pd

import data_provider
from data_provider import (
    _chart_payload_to_dataframe,
    _download_weekly_from_yahoo,
    _drop_incomplete_current_week,
    _read_local_csv,
    _resample_daily_to_weekly,
    _yahoo_query_ticker,
    load_weekly_data_resilient,
)


def test_chart_payload_to_dataframe_normalizes_yahoo_weekly_rows() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704412800, 1705017600],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 101.0],
                                "high": [105.0, 106.0],
                                "low": [99.0, 100.0],
                                "close": [104.0, 105.0],
                                "volume": [1000, 1100],
                            }
                        ],
                        "adjclose": [{"adjclose": [104.0, 105.0]}],
                    },
                }
            ],
            "error": None,
        }
    }

    result = _chart_payload_to_dataframe(payload)

    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume", "Adj Close"]
    assert isinstance(result.index, pd.DatetimeIndex)
    assert result.iloc[0]["Open"] == 100.0
    assert result.iloc[1]["Close"] == 105.0


def test_drop_incomplete_current_week_removes_all_rows_in_current_week(monkeypatch) -> None:
    class FixedTimestamp(pd.Timestamp):
        @classmethod
        def today(cls, tz=None):
            return cls("2026-05-20")

    monkeypatch.setattr(pd, "Timestamp", FixedTimestamp)
    data = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0, 4.0]},
        index=pd.to_datetime(["2026-05-08", "2026-05-15", "2026-05-18", "2026-05-19"]),
    )

    result = _drop_incomplete_current_week(data)

    assert result.index.strftime("%Y-%m-%d").tolist() == ["2026-05-08", "2026-05-15"]


def test_resample_daily_to_weekly_uses_monday_label_and_weekly_ohlcv() -> None:
    daily = pd.DataFrame(
        {
            "Open": [84.26, 85.00, 86.00, 87.00, 86.50],
            "High": [85.00, 87.83, 87.00, 87.20, 87.00],
            "Low": [84.08, 84.70, 85.80, 86.40, 86.20],
            "Close": [84.90, 86.20, 86.80, 86.50, 87.37],
            "Volume": [10, 20, 30, 40, 50],
            "Adj Close": [84.90, 86.20, 86.80, 86.50, 87.37],
        },
        index=pd.to_datetime(
            ["2025-08-18", "2025-08-19", "2025-08-20", "2025-08-21", "2025-08-22"]
        ),
    )

    result = _resample_daily_to_weekly(daily)

    assert result.index.strftime("%Y-%m-%d").tolist() == ["2025-08-18"]
    row = result.iloc[0]
    assert row["Open"] == 84.26
    assert row["High"] == 87.83
    assert row["Low"] == 84.08
    assert row["Close"] == 87.37
    assert row["Volume"] == 150


def test_resample_daily_to_weekly_can_keep_current_week(monkeypatch) -> None:
    class FixedTimestamp(pd.Timestamp):
        @classmethod
        def today(cls, tz=None):
            return cls("2026-05-20")

    monkeypatch.setattr(pd, "Timestamp", FixedTimestamp)
    daily = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [12.0, 13.0],
            "Low": [9.0, 10.0],
            "Close": [11.0, 12.0],
            "Volume": [100, 200],
        },
        index=pd.to_datetime(["2026-05-18", "2026-05-19"]),
    )

    result = _resample_daily_to_weekly(daily, include_current_week=True)

    assert result.index.strftime("%Y-%m-%d").tolist() == ["2026-05-18"]
    assert result.iloc[0]["Close"] == 12.0


def test_read_local_csv_can_keep_or_drop_current_week(tmp_path, monkeypatch) -> None:
    class FixedTimestamp(pd.Timestamp):
        @classmethod
        def today(cls, tz=None):
            return cls("2026-05-20")

    monkeypatch.setattr(pd, "Timestamp", FixedTimestamp)
    csv_path = tmp_path / "TEST.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Date,Open,High,Low,Close,Volume",
                "2026-05-11,1,2,1,2,100",
                "2026-05-18,2,3,2,3,200",
            ]
        ),
        encoding="utf-8",
    )

    dropped = _read_local_csv(csv_path)
    kept = _read_local_csv(csv_path, include_current_week=True)

    assert dropped.index.strftime("%Y-%m-%d").tolist() == ["2026-05-11"]
    assert kept.index.strftime("%Y-%m-%d").tolist() == ["2026-05-11", "2026-05-18"]


def test_yahoo_query_ticker_uses_yahoo_dash_for_dot_tickers() -> None:
    assert _yahoo_query_ticker("brk.b") == "BRK-B"
    assert _yahoo_query_ticker("BF.B") == "BF-B"
    assert _yahoo_query_ticker("AAPL") == "AAPL"


def test_download_weekly_from_yahoo_does_not_fall_back_to_raw_weekly(monkeypatch) -> None:
    raw_chart_calls = []

    def fake_daily_download(ticker: str, include_current_week: bool = False) -> pd.DataFrame:
        raise RuntimeError("daily unavailable")

    def fake_raw_chart(*args, **kwargs) -> pd.DataFrame:
        raw_chart_calls.append((args, kwargs))
        raise RuntimeError("raw 1wk fallback should not be used")

    def fake_yfinance_download(ticker: str, include_current_week: bool = False) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Open": [1.0],
                "High": [2.0],
                "Low": [1.0],
                "Close": [2.0],
                "Volume": [100],
            },
            index=pd.to_datetime(["2026-05-11"]),
        )

    monkeypatch.setattr(
        data_provider,
        "_download_daily_then_resample_from_yahoo",
        fake_daily_download,
    )
    monkeypatch.setattr(data_provider, "_download_from_yahoo_chart", fake_raw_chart)
    monkeypatch.setattr(data_provider, "_download_with_yfinance", fake_yfinance_download)

    result = _download_weekly_from_yahoo("BRK.B")

    assert result.index.strftime("%Y-%m-%d").tolist() == ["2026-05-11"]
    assert raw_chart_calls == []


def test_resilient_weekly_loader_refreshes_cache_older_than_expected_week(
    tmp_path,
    monkeypatch,
) -> None:
    cache_path = tmp_path / "^GSPC.csv"
    cache_path.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-07-27,1,2,1,2,100\n",
        encoding="utf-8",
    )
    refreshed = pd.DataFrame(
        {
            "Open": [2.0],
            "High": [3.0],
            "Low": [2.0],
            "Close": [3.0],
            "Volume": [200.0],
        },
        index=pd.to_datetime(["2026-08-17"]),
    )
    calls = []

    def fake_download(ticker: str, include_current_week: bool = False) -> pd.DataFrame:
        calls.append((ticker, include_current_week))
        return refreshed

    monkeypatch.setattr(data_provider, "_download_weekly_from_yahoo", fake_download)

    result = load_weekly_data_resilient(
        "^GSPC",
        data_dir=tmp_path,
        include_current_week=True,
        expected_latest_date="2026-08-17",
        max_cache_age_seconds=None,
    )

    assert result.source == "download"
    assert result.data.index[-1] == pd.Timestamp("2026-08-17")
    assert calls == [("^GSPC", True)]


def test_resilient_weekly_loader_uses_valid_stale_cache_when_refresh_fails(
    tmp_path,
    monkeypatch,
) -> None:
    cache_path = tmp_path / "^GSPC.csv"
    cache_path.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-07-27,1,2,1,2,100\n",
        encoding="utf-8",
    )

    def failing_download(ticker: str, include_current_week: bool = False) -> pd.DataFrame:
        raise RuntimeError("network down")

    monkeypatch.setattr(data_provider, "_download_weekly_from_yahoo", failing_download)

    result = load_weekly_data_resilient(
        "^GSPC",
        data_dir=tmp_path,
        include_current_week=True,
        force_refresh=True,
    )

    assert result.used_stale_cache is True
    assert result.data.index[-1] == pd.Timestamp("2026-07-27")
    assert "저장 데이터 사용" in result.warning
    assert "2026-07-27" in result.warning


def test_weekly_bar_is_in_progress_until_friday_close_in_new_york() -> None:
    from data_provider import weekly_bar_in_progress

    week = pd.Timestamp("2026-09-21")

    assert weekly_bar_in_progress(week, now=pd.Timestamp("2026-09-25 15:59"))
    assert not weekly_bar_in_progress(week, now=pd.Timestamp("2026-09-25 16:00"))
    # Saturday 04:00 in Korea is still Friday afternoon in New York.
    korea_saturday = pd.Timestamp("2026-09-26 04:00", tz="Asia/Seoul")
    assert weekly_bar_in_progress(week, now=korea_saturday)
