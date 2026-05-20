"""Alpaca paper-trading connector — free, runs on macOS.

Trades the GLD gold ETF (price tracks gold). Paper money only.
Get free API keys: https://alpaca.markets -> sign up -> Paper Trading -> API Keys.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

_trading: TradingClient | None = None
_data: StockHistoricalDataClient | None = None

_TF = {
    "M15": TimeFrame(15, TimeFrameUnit.Minute),
    "M30": TimeFrame(30, TimeFrameUnit.Minute),
    "H1": TimeFrame(1, TimeFrameUnit.Hour),
    "D1": TimeFrame(1, TimeFrameUnit.Day),
}


def connect(cfg) -> bool:
    global _trading, _data
    if not cfg.alpaca_key or not cfg.alpaca_secret:
        print("Missing ALPACA_KEY / ALPACA_SECRET — fill them into .env")
        return False
    try:
        _trading = TradingClient(cfg.alpaca_key, cfg.alpaca_secret, paper=True)
        _data = StockHistoricalDataClient(cfg.alpaca_key, cfg.alpaca_secret)
        acc = _trading.get_account()
    except Exception as e:
        print("Alpaca connection failed:", e)
        return False
    print(f"Connected to Alpaca PAPER | equity ${float(acc.equity):,.2f} "
          f"| buying power ${float(acc.buying_power):,.2f}")
    return True


def shutdown():
    pass


def account():
    return _trading.get_account()


def pnl_today() -> float:
    """Today's total P/L = current equity minus equity at yesterday's close."""
    acc = _trading.get_account()
    return float(acc.equity) - float(acc.last_equity)


def get_bars(symbol: str, timeframe: str, n: int):
    start = datetime.now(timezone.utc) - timedelta(days=120)
    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=_TF[timeframe],
                           start=start, feed=DataFeed.IEX)
    try:
        bars = _data.get_stock_bars(req).df
    except Exception as e:
        print("get_bars failed:", e)
        return None
    if bars is None or bars.empty:
        return None
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol, level="symbol")
    bars = bars.rename(columns=str.lower)
    df = bars[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    return df.tail(n)


def get_position(symbol: str):
    """Return the open position object for symbol, or None."""
    try:
        return _trading.get_open_position(symbol)
    except Exception:
        return None


def market_order(symbol: str, side: str, qty: int):
    """Submit a simple market order. side = 'buy' or 'sell'."""
    req = MarketOrderRequest(
        symbol=symbol,
        qty=int(qty),
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    try:
        return _trading.submit_order(req)
    except Exception as e:
        print("market_order failed:", e)
        return None


def close_position(symbol: str):
    try:
        return _trading.close_position(symbol)
    except Exception as e:
        print("close_position failed:", e)
        return None
