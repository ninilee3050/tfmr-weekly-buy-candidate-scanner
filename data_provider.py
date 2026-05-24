from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd


DATA_DIR = Path("data")
REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


class DataLoadError(RuntimeError):
    """Raised when Yahoo-style daily data cannot be loaded."""


def normalize_ticker(ticker: str) -> str:
    cleaned = ticker.strip().upper()
    if not cleaned:
        raise ValueError("티커를 입력해 주세요.")
    return cleaned


def load_weekly_data(
    ticker: str,
    data_dir: Path | str = DATA_DIR,
    include_current_week: bool = False,
    force_refresh: bool = False,
) -> pd.DataFrame:
    ticker = normalize_ticker(ticker)
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    csv_path = data_dir / f"{ticker}.csv"

    if csv_path.exists() and not force_refresh:
        data = _read_local_csv(csv_path)
        return data if include_current_week else drop_current_week(data)

    weekly = _download_daily_then_resample(ticker)
    if weekly.empty:
        raise DataLoadError(f"{ticker} 주봉 데이터가 비어 있습니다.")

    weekly.to_csv(csv_path, index_label="Date", encoding="utf-8-sig")
    return weekly if include_current_week else drop_current_week(weekly)


def drop_current_week(data: pd.DataFrame, today: pd.Timestamp | str | None = None) -> pd.DataFrame:
    if data.empty:
        return data
    current_week_start = monday_week_start(today)
    index = pd.DatetimeIndex(data.index).normalize()
    return data[index < current_week_start]


def resample_daily_to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    data = daily.sort_index().copy()
    data["_WeekStart"] = monday_week_start_index(data.index)
    weekly = data.groupby("_WeekStart").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    weekly.index = pd.DatetimeIndex(weekly.index)
    weekly.index.name = "Date"
    return weekly.dropna(subset=REQUIRED_COLUMNS)


def monday_week_start(date: pd.Timestamp | str | None = None) -> pd.Timestamp:
    value = pd.Timestamp.today() if date is None else pd.Timestamp(date)
    normalized = value.normalize()
    return normalized - pd.Timedelta(days=normalized.weekday())


def monday_week_start_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    normalized = pd.DatetimeIndex(index).normalize()
    return normalized - pd.to_timedelta(normalized.weekday, unit="D")


def _read_local_csv(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    return _normalize_ohlcv_dataframe(raw)


def _download_daily_then_resample(ticker: str) -> pd.DataFrame:
    errors: list[str] = []
    try:
        daily = _download_daily_with_yfinance(ticker)
        return resample_daily_to_weekly(daily)
    except Exception as exc:  # pragma: no cover - network dependent
        errors.append(f"yfinance: {exc}")

    try:
        daily = _download_daily_from_yahoo_chart(ticker)
        return resample_daily_to_weekly(daily)
    except Exception as exc:  # pragma: no cover - network dependent
        errors.append(f"Yahoo chart API: {exc}")

    raise DataLoadError(
        f"{ticker} 데이터를 불러오지 못했습니다. 인터넷 연결과 티커를 확인해 주세요. "
        f"상세: {' / '.join(errors)}"
    )


def _download_daily_from_yahoo_chart(ticker: str) -> pd.DataFrame:
    period2 = int(time.time())
    query = (
        f"?period1=0&period2={period2}"
        "&interval=1d&events=history&includeAdjustedClose=true"
    )
    url = YAHOO_CHART_URL.format(ticker=quote(_yahoo_symbol(ticker), safe="")) + query
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
            ),
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise DataLoadError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise DataLoadError(str(exc.reason)) from exc

    return _chart_payload_to_dataframe(payload)


def _download_daily_with_yfinance(ticker: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DataLoadError("yfinance가 설치되어 있지 않습니다.") from exc

    raw = yf.download(
        _yahoo_symbol(ticker),
        period="max",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return _normalize_ohlcv_dataframe(raw.reset_index())


def _chart_payload_to_dataframe(payload: dict) -> pd.DataFrame:
    chart = payload.get("chart", {})
    if chart.get("error"):
        error = chart["error"]
        raise DataLoadError(error.get("description") or error.get("code") or "Yahoo 오류")

    results = chart.get("result") or []
    if not results:
        raise DataLoadError("Yahoo 응답에 가격 데이터가 없습니다.")

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    rows = {
        "Date": [datetime.fromtimestamp(ts, tz=timezone.utc).date() for ts in timestamps],
        "Open": quote_data.get("open", []),
        "High": quote_data.get("high", []),
        "Low": quote_data.get("low", []),
        "Close": quote_data.get("close", []),
        "Volume": quote_data.get("volume", []),
    }
    return _normalize_ohlcv_dataframe(pd.DataFrame(rows))


def _normalize_ohlcv_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    data = raw.copy()
    if data.empty and len(data.columns) == 0:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    data.columns = [str(column).strip() for column in data.columns]
    lower_to_original = {column.lower(): column for column in data.columns}
    rename_map = {}
    for expected in ["Date", *REQUIRED_COLUMNS]:
        original = lower_to_original.get(expected.lower())
        if original:
            rename_map[original] = expected
    data = data.rename(columns=rename_map)

    if "Date" not in data.columns:
        data = data.rename(columns={data.columns[0]: "Date"})

    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise DataLoadError(f"가격 데이터에 필요한 컬럼이 없습니다: {', '.join(missing)}")

    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"]).sort_values("Date").set_index("Date")
    for column in REQUIRED_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=REQUIRED_COLUMNS)
    data.index = pd.DatetimeIndex(data.index).normalize()
    data.index.name = "Date"
    return data


def _yahoo_symbol(ticker: str) -> str:
    return normalize_ticker(ticker).replace(".", "-")
