from __future__ import annotations

import pandas as pd
import pytest

import app
import data_provider
import market_cap_provider
import weekly_scan
from market_cap_provider import MarketCapCompany, MarketCapLoadError


def test_market_cap_provider_does_not_return_fallback_on_live_lookup_failure(monkeypatch) -> None:
    def fail_live_lookup() -> str:
        raise MarketCapLoadError("site down")

    monkeypatch.setattr(market_cap_provider, "_download_stockanalysis_page", fail_live_lookup)

    with pytest.raises(MarketCapLoadError):
        market_cap_provider.fetch_us_top_market_cap(limit=100)

    assert not hasattr(market_cap_provider, "_fallback_top100")


def test_parse_stockanalysis_market_cap_table_extracts_ranked_companies() -> None:
    html = """
    <html>
      <body>
        <table>
          <thead>
            <tr>
              <th>No.</th>
              <th>Symbol</th>
              <th>Company Name</th>
              <th>Market Cap</th>
              <th>Stock Price</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>1</td>
              <td>NVDA</td>
              <td>NVIDIA Corporation</td>
              <td>5.34T</td>
              <td>220.61</td>
            </tr>
            <tr>
              <td>2</td>
              <td>GOOGL</td>
              <td>Alphabet Inc.</td>
              <td>4.70T</td>
              <td>387.66</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    companies = market_cap_provider.parse_stockanalysis_market_cap_table(html)

    assert len(companies) == 2
    assert companies[0] == MarketCapCompany(1, "NVDA", "NVIDIA Corporation", "5.34T")
    assert companies[1].ticker == "GOOGL"


def test_central_search_uses_force_refresh(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    expected = pd.DataFrame({"Open": [1], "Close": [1]})

    def fake_load_weekly_data(
        ticker: str,
        include_current_week: bool,
        force_refresh: bool,
    ) -> pd.DataFrame:
        calls.append(
            {
                "ticker": ticker,
                "include_current_week": include_current_week,
                "force_refresh": force_refresh,
            }
        )
        return expected

    monkeypatch.setattr(app, "load_weekly_data", fake_load_weekly_data)

    result = app.load_confirmed_weekly_for_search("AAPL")

    assert result is expected
    assert calls == [
        {
            "ticker": "AAPL",
            "include_current_week": False,
            "force_refresh": True,
        }
    ]


def test_central_data_load_excludes_current_week_from_cached_weekly_csv(tmp_path) -> None:
    current_week = data_provider.monday_week_start()
    previous_week = current_week - pd.Timedelta(weeks=1)
    csv_path = tmp_path / "TEST.csv"
    pd.DataFrame(
        [
            _ohlcv_row(previous_week, 100),
            _ohlcv_row(current_week, 110),
        ]
    ).to_csv(csv_path, index=False)

    central = data_provider.load_weekly_data("TEST", data_dir=tmp_path, include_current_week=False)
    scanner = data_provider.load_weekly_data("TEST", data_dir=tmp_path, include_current_week=True)

    assert previous_week in central.index
    assert current_week not in central.index
    assert current_week in scanner.index


def test_top100_scanner_requests_and_detects_current_week(monkeypatch) -> None:
    current_week = data_provider.monday_week_start()
    calls: list[bool] = []

    def fake_load_weekly_data(
        ticker: str,
        data_dir: object,
        include_current_week: bool,
        force_refresh: bool,
    ) -> pd.DataFrame:
        calls.append(include_current_week)
        return _current_week_buy_base_frame(current_week)

    monkeypatch.setattr(weekly_scan, "load_weekly_data", fake_load_weekly_data)
    companies = [MarketCapCompany(1, "TEST", "Test Corp", "$1.00 T")]

    candidates, failures = weekly_scan.scan_companies(
        companies,
        scan_date=current_week,
        force_refresh=True,
    )

    assert calls == [True]
    assert failures.empty
    assert len(candidates) == 1
    assert candidates.iloc[0]["주봉시작일"] == current_week


def test_weekly_scan_fails_when_live_top100_lookup_fails(monkeypatch) -> None:
    def fail_top100_lookup(limit: int) -> list[MarketCapCompany]:
        raise MarketCapLoadError("live lookup failed")

    monkeypatch.setattr(weekly_scan, "fetch_us_top_market_cap", fail_top100_lookup)

    with pytest.raises(MarketCapLoadError):
        weekly_scan.scan_top100(limit=100)


def _ohlcv_row(date: pd.Timestamp, close: float) -> dict[str, object]:
    return {
        "Date": date,
        "Open": close - 1,
        "High": close + 1,
        "Low": close - 2,
        "Close": close,
        "Volume": 1000,
    }


def _current_week_buy_base_frame(current_week: pd.Timestamp) -> pd.DataFrame:
    dates = [current_week - pd.Timedelta(weeks=2), current_week - pd.Timedelta(weeks=1), current_week]
    rows = [
        {
            "Open": 100,
            "Close": 99,
            "MA5": 101,
            "MA20": 100,
            "MA50": 101,
            "MA150": 120,
            "MA200": 100,
        },
        {
            "Open": 104,
            "Close": 105,
            "MA5": 104,
            "MA20": 102,
            "MA50": 101,
            "MA150": 120,
            "MA200": 100,
        },
        {
            "Open": 96,
            "Close": 94,
            "MA5": 97,
            "MA20": 100,
            "MA50": 99,
            "MA150": 120,
            "MA200": 100,
        },
    ]
    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates, name="Date"))
