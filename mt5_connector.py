"""MetaTrader 5 wrapper — data + order execution.

WINDOWS ONLY. The `MetaTrader5` package does not run on macOS/Linux.
Run this (and bot.py) on a Windows machine or a Windows VPS.
"""
from datetime import datetime, timezone

import pandas as pd
import MetaTrader5 as mt5

_TF = {
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def connect(cfg) -> bool:
    ok = mt5.initialize(path=cfg.mt5_path) if cfg.mt5_path else mt5.initialize()
    if not ok:
        print("MT5 initialize() failed:", mt5.last_error())
        return False
    if cfg.mt5_login:
        if not mt5.login(cfg.mt5_login, password=cfg.mt5_password, server=cfg.mt5_server):
            print("MT5 login() failed:", mt5.last_error())
            return False
    if not mt5.symbol_select(cfg.symbol, True):
        print(f"Warning: could not select symbol {cfg.symbol}")
    acc = mt5.account_info()
    if acc and acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        print("=" * 60)
        print("WARNING: this is NOT a demo account. Trading with REAL money.")
        print("=" * 60)
    return True


def shutdown():
    mt5.shutdown()


def account_info():
    return mt5.account_info()


def symbol_info(symbol):
    return mt5.symbol_info(symbol)


def get_rates(symbol: str, timeframe: str, n: int):
    rates = mt5.copy_rates_from_pos(symbol, _TF[timeframe], 0, n)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").rename(columns={"tick_volume": "volume"})
    return df[["open", "high", "low", "close", "volume"]]


def get_positions(symbol: str, magic: int):
    pos = mt5.positions_get(symbol=symbol)
    return [p for p in (pos or []) if p.magic == magic]


def market_order(symbol: str, side: str, lots: float, sl: float, tp: float, magic: int):
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if side == "buy" else tick.bid
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": magic,
        "comment": "gold-bot bollinger",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        print("order_send failed:", getattr(res, "retcode", None), getattr(res, "comment", None))
    return res


def close_position(p):
    tick = mt5.symbol_info_tick(p.symbol)
    if p.type == mt5.POSITION_TYPE_BUY:
        order_type, price = mt5.ORDER_TYPE_SELL, tick.bid
    else:
        order_type, price = mt5.ORDER_TYPE_BUY, tick.ask
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": p.symbol,
        "volume": p.volume,
        "type": order_type,
        "position": p.ticket,
        "price": price,
        "deviation": 20,
        "magic": p.magic,
        "comment": "gold-bot close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        print("close failed:", getattr(res, "retcode", None), getattr(res, "comment", None))
    return res


def realized_pnl_today(magic: int) -> float:
    """Sum of closed-deal profit for this bot since 00:00 UTC today."""
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    deals = mt5.history_deals_get(start, now)
    return sum(d.profit for d in (deals or []) if d.magic == magic)
