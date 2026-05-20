"""Central config for the gold bot. Values come from .env (see .env.example)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass
class Config:
    # --- MT5 connection (use a DEMO account first) ---
    mt5_login: int = int(os.getenv("MT5_LOGIN") or "0")
    mt5_password: str = os.getenv("MT5_PASSWORD", "")
    mt5_server: str = os.getenv("MT5_SERVER", "")
    mt5_path: str = os.getenv("MT5_PATH", "")  # path to terminal64.exe, optional

    # --- Alpaca paper trading (free, macOS-friendly — used by bot.py) ---
    alpaca_key: str = os.getenv("ALPACA_KEY", "")
    alpaca_secret: str = os.getenv("ALPACA_SECRET", "")

    symbol: str = os.getenv("SYMBOL", "GLD")
    timeframe: str = os.getenv("TIMEFRAME", "H1")

    # --- Strategy: Bollinger mean-reversion with a trend filter ---
    # Values below were chosen by optimize.py (best out-of-sample setting).
    bb_period: int = 20
    bb_std: float = 2.5
    ema_trend: int = 200          # only take longs above it, shorts below it
    rsi_period: int = 14
    rsi_oversold: float = 40.0
    rsi_overbought: float = 60.0
    atr_period: int = 14
    atr_sl_mult: float = 1.0      # stop loss = entry -/+ atr_sl_mult * ATR
    allow_shorts: bool = os.getenv("ALLOW_SHORTS", "true").lower() == "true"

    # --- Risk management ---
    risk_per_trade_pct: float = _f("RISK_PER_TRADE_PCT", 1.0)   # % of balance risked per trade
    max_daily_loss_pct: float = _f("MAX_DAILY_LOSS_PCT", 3.0)   # stop trading for the day past this
    max_open_positions: int = 1
    magic: int = 20260520         # tags this bot's orders so it ignores manual trades


CONFIG = Config()
