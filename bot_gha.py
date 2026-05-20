"""One-shot bot for GitHub Actions — runs once per hour during US market hours.

Alpaca bracket orders handle SL/TP natively, so no state.json needed.
GitHub Actions cron triggers this every hour Mon-Fri during market hours.
Reads params.json (written by optimize_gha.py) to use latest tuned parameters.
"""
import json
import os
import sys
from datetime import datetime, timezone

import alpaca_connector as broker
import risk
import strategy
from config import CONFIG

from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)


def log(msg: str):
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {msg}", flush=True)


def load_params(cfg):
    """Override cfg with optimized params from params.json if available."""
    if not os.path.exists("params.json"):
        return cfg
    with open("params.json") as f:
        p = json.load(f)
    for key in ["bb_std", "rsi_oversold", "rsi_overbought", "atr_sl_mult", "allow_shorts"]:
        if key in p:
            setattr(cfg, key, p[key])
    log(f"Loaded params.json ({p.get('updated','?')}): "
        f"bb_std={cfg.bb_std} rsi_os={cfg.rsi_oversold} "
        f"atr_sl={cfg.atr_sl_mult} shorts={cfg.allow_shorts}")
    return cfg


def is_market_open() -> bool:
    """Simple check: Mon-Fri 13:35-19:55 UTC = ~9:35am-3:55pm ET."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    minutes = now.hour * 60 + now.minute
    return 13 * 60 + 35 <= minutes <= 19 * 60 + 55


def bracket_order(cfg, side: str, qty: int, sl_price: float, tp_price: float):
    """Submit market entry with bracket SL + TP."""
    req = MarketOrderRequest(
        symbol=cfg.symbol,
        qty=int(qty),
        side=OrderSide.BUY if side == "long" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=round(tp_price, 2)),
        stop_loss=StopLossRequest(stop_price=round(sl_price, 2)),
    )
    try:
        return broker._trading.submit_order(req)
    except Exception as e:
        log(f"bracket_order failed: {e}")
        return None


def run():
    cfg = load_params(CONFIG)
    if not broker.connect(cfg):
        log("Could not connect to Alpaca — check secrets. Exiting.")
        sys.exit(1)

    if not is_market_open():
        log("Market closed — nothing to do.")
        sys.exit(0)

    # If position already open, Alpaca manages SL/TP — nothing to do
    if broker.get_position(cfg.symbol) is not None:
        log("Position already open — Alpaca managing SL/TP. Done.")
        sys.exit(0)

    # Daily loss check
    acc = broker.account()
    equity = float(acc.equity)
    pnl = broker.pnl_today()
    if pnl <= -abs(equity * cfg.max_daily_loss_pct / 100.0):
        log(f"Daily loss limit hit ({pnl:+.2f}). No new trades today.")
        sys.exit(0)

    # Fetch bars and compute signal
    df = broker.get_bars(cfg.symbol, cfg.timeframe, 320)
    if df is None or len(df) < cfg.ema_trend + 5:
        log("Not enough bars — skipping.")
        sys.exit(0)

    df_closed = df.iloc[:-1]
    sig = strategy.signal(strategy.add_indicators(df_closed, cfg), cfg)
    log(f"close={sig['price']:.2f} | long={sig['long_entry']} short={sig['short_entry']}")

    if not sig["long_entry"] and not sig["short_entry"]:
        log("No signal — done.")
        sys.exit(0)

    if sig["long_entry"]:
        side = "long"
        sl = round(sig["price"] - cfg.atr_sl_mult * sig["atr"], 2)
        tp = round(sig["bb_mid"], 2)
    else:
        side = "short"
        sl = round(sig["price"] + cfg.atr_sl_mult * sig["atr"], 2)
        tp = round(sig["bb_mid"], 2)

    stop_distance = abs(sig["price"] - sl)
    qty = int(risk.position_size(equity, cfg.risk_per_trade_pct, stop_distance,
                                 contract_size=1, min_lot=1,
                                 max_lot=1_000_000, lot_step=1))
    qty = min(qty, int(equity * 0.95 / sig["price"]))
    if qty < 1:
        log("Signal skipped — position size rounds to 0 shares.")
        sys.exit(0)

    order = bracket_order(cfg, side, qty, sl, tp)
    if order:
        log(f"ENTER {side} {qty} {cfg.symbol} @ ~{sig['price']:.2f}  SL {sl:.2f}  TP {tp:.2f}")
    else:
        log("Order failed.")


if __name__ == "__main__":
    run()
