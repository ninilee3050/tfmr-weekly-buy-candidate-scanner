from __future__ import annotations

import pandas as pd


def calculate_indicators(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    close = result["Close"]

    result["MA_5"] = close.rolling(5).mean()
    result["MA_20"] = close.rolling(20).mean()
    result["MA_50"] = close.rolling(50).mean()
    result["MA_150"] = close.rolling(150).mean()
    result["MA_200"] = close.rolling(200).mean()
    result["Volume_MA_50"] = result["Volume"].rolling(50).mean()

    result["Momentum"] = calculate_momentum(close, period=14)
    macd, signal, histogram = calculate_macd(close, fast=12, slow=26, signal=9)
    result["MACD"] = macd
    result["Signal"] = signal
    result["Histogram"] = histogram
    result["RSI"] = calculate_rsi(close, period=14)
    result["MFI"] = calculate_mfi(
        result["High"],
        result["Low"],
        result["Close"],
        result["Volume"],
        period=14,
    )
    return result


def calculate_momentum(close: pd.Series, period: int = 14) -> pd.Series:
    return close - close.shift(period)


def calculate_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ema = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd = fast_ema - slow_ema
    signal_line = macd.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss == 0), 50)
    return rsi


def calculate_mfi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = 14,
) -> pd.Series:
    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume
    direction = typical_price.diff()

    positive_flow = money_flow.where(direction > 0, 0.0)
    negative_flow = money_flow.where(direction < 0, 0.0)

    positive_sum = positive_flow.rolling(period, min_periods=period).sum()
    negative_sum = negative_flow.rolling(period, min_periods=period).sum()
    money_ratio = positive_sum / negative_sum
    mfi = 100 - (100 / (1 + money_ratio))

    mfi = mfi.mask((negative_sum == 0) & (positive_sum > 0), 100)
    mfi = mfi.mask((positive_sum == 0) & (negative_sum > 0), 0)
    mfi = mfi.mask((positive_sum == 0) & (negative_sum == 0), 50)
    return mfi
