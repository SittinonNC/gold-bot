"""Indicators and the Bollinger mean-reversion signal.

Pure pandas — no TA-Lib needed. Runs anywhere (used by both backtest and live bot).
"""
import pandas as pd


def bollinger(close: pd.Series, period: int, std: float):
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    return mid - std * sd, mid, mid + std * sd


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def add_indicators(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Return a copy of df with all indicator columns attached."""
    df = df.copy()
    df["bb_lower"], df["bb_mid"], df["bb_upper"] = bollinger(df["close"], cfg.bb_period, cfg.bb_std)
    df["ema_trend"] = ema(df["close"], cfg.ema_trend)
    df["rsi"] = rsi(df["close"], cfg.rsi_period)
    df["atr"] = atr(df, cfg.atr_period)
    return df


def signal(df: pd.DataFrame, cfg) -> dict:
    """Evaluate the latest CLOSED bar.

    Long  : price below lower band + above EMA200 (uptrend) + RSI oversold
    Short : price above upper band + below EMA200 (downtrend) + RSI overbought
    Exit  : price reverts to the middle band (the take-profit target)
    """
    row = df.iloc[-1]
    long_entry = (
        row["close"] < row["bb_lower"]
        and row["close"] > row["ema_trend"]
        and row["rsi"] < cfg.rsi_oversold
    )
    short_entry = (
        cfg.allow_shorts
        and row["close"] > row["bb_upper"]
        and row["close"] < row["ema_trend"]
        and row["rsi"] > cfg.rsi_overbought
    )
    return {
        "long_entry": bool(long_entry),
        "short_entry": bool(short_entry),
        "exit_long": bool(row["close"] >= row["bb_mid"]),
        "exit_short": bool(row["close"] <= row["bb_mid"]),
        "price": float(row["close"]),
        "atr": float(row["atr"]),
        "bb_mid": float(row["bb_mid"]),
    }
