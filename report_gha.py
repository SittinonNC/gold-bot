"""Generates docs/status.json for the GitHub Pages dashboard.

Fetches live data from Alpaca + computes current signal, writes a single JSON
file that the static dashboard reads. Run by GitHub Actions after bot_gha.py.
"""
import json
import os
from datetime import datetime, timezone

import alpaca_connector as broker
import strategy
from config import CONFIG

from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest


def run():
    cfg = CONFIG
    if not broker.connect(cfg):
        print("Could not connect to Alpaca — skipping report.")
        return

    acc   = broker.account()
    pos   = broker.get_position(cfg.symbol)
    pnl   = broker.pnl_today()
    equity = float(acc.equity)

    # ── account ────────────────────────────────────────────────────────────
    account_data = {
        "equity":        round(equity, 2),
        "buying_power":  round(float(acc.buying_power), 2),
        "pnl_today":     round(pnl, 2),
        "pnl_today_pct": round(pnl / (equity - pnl) * 100, 2) if equity != pnl else 0,
    }

    # ── open position ───────────────────────────────────────────────────────
    position_data = None
    if pos:
        position_data = {
            "symbol":         pos.symbol,
            "side":           pos.side.value if hasattr(pos.side, "value") else str(pos.side),
            "qty":            float(pos.qty),
            "entry_price":    round(float(pos.avg_entry_price), 2),
            "current_price":  round(float(pos.current_price), 2),
            "unrealized_pl":  round(float(pos.unrealized_pl), 2),
            "unrealized_plpc": round(float(pos.unrealized_plpc) * 100, 2),
        }

    # ── current signal ──────────────────────────────────────────────────────
    signal_data = {}
    df = broker.get_bars(cfg.symbol, cfg.timeframe, 320)
    if df is not None and len(df) >= cfg.ema_trend + 5:
        df_closed = df.iloc[:-1]
        df_ind    = strategy.add_indicators(df_closed, cfg)
        sig       = strategy.signal(df_ind, cfg)
        last      = df_ind.iloc[-1]
        signal_data = {
            "price":       round(sig["price"], 2),
            "bb_lower":    round(float(last["bb_lower"]), 2),
            "bb_mid":      round(float(last["bb_mid"]), 2),
            "bb_upper":    round(float(last["bb_upper"]), 2),
            "ema200":      round(float(last["ema_trend"]), 2),
            "rsi":         round(float(last["rsi"]), 1),
            "atr":         round(float(last["atr"]), 2),
            "long_entry":  bool(sig["long_entry"]),
            "short_entry": bool(sig["short_entry"]),
        }

    # ── recent orders ───────────────────────────────────────────────────────
    recent_orders = []
    try:
        req    = GetOrdersRequest(status=QueryOrderStatus.CLOSED,
                                  limit=20, symbols=[cfg.symbol])
        orders = broker._trading.get_orders(filter=req)
        for o in orders:
            recent_orders.append({
                "side":          o.side.value if hasattr(o.side, "value") else str(o.side),
                "qty":           float(o.qty or 0),
                "filled_price":  round(float(o.filled_avg_price), 2) if o.filled_avg_price else None,
                "filled_at":     o.filled_at.isoformat() if o.filled_at else None,
                "status":        o.status.value if hasattr(o.status, "value") else str(o.status),
                "order_class":   o.order_class.value if hasattr(o.order_class, "value") else str(o.order_class),
            })
    except Exception as e:
        print(f"Could not fetch orders: {e}")

    # ── params ──────────────────────────────────────────────────────────────
    params_data = {}
    if os.path.exists("params.json"):
        with open("params.json") as f:
            params_data = json.load(f)

    # ── write ───────────────────────────────────────────────────────────────
    status = {
        "updated":       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "symbol":        cfg.symbol,
        "timeframe":     cfg.timeframe,
        "account":       account_data,
        "position":      position_data,
        "signal":        signal_data,
        "recent_orders": recent_orders,
        "params":        params_data,
    }

    os.makedirs("docs", exist_ok=True)
    with open("docs/status.json", "w") as f:
        json.dump(status, f, indent=2)
    print(f"Dashboard data written → docs/status.json  (equity ${equity:,.2f})")


if __name__ == "__main__":
    run()
