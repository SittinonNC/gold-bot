"""Live paper-trading bot — Bollinger mean-reversion on the GLD gold ETF
via Alpaca. FREE, runs on macOS. Paper money only.

    python bot.py

The bot enters on a new closed bar and manages its own stop-loss / take-profit
(checked every ~60s). Open-trade levels are saved to logs/state.json so they
survive a restart. Stop with Ctrl+C. Activity is logged to logs/bot.log.
"""
import json
import os
import time
from datetime import datetime, timezone

import alpaca_connector as broker
import risk
import strategy
from config import CONFIG

os.makedirs("logs", exist_ok=True)
STATE_FILE = "logs/state.json"


def log(msg: str):
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {msg}"
    print(line)
    with open("logs/bot.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def clear_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


def manage_position(cfg, price_now: float):
    """Close the open trade if price hit our stop-loss or take-profit."""
    pos = broker.get_position(cfg.symbol)
    state = load_state()

    if pos is None:
        if state is not None:        # position already gone — sync state
            clear_state()
        return

    if state is None:                # untracked position — close for a clean start
        log("Found an untracked position — closing it to start clean.")
        broker.close_position(cfg.symbol)
        return

    if state["side"] == "long":
        hit_sl, hit_tp = price_now <= state["sl"], price_now >= state["tp"]
    else:
        hit_sl, hit_tp = price_now >= state["sl"], price_now <= state["tp"]

    if hit_sl or hit_tp:
        broker.close_position(cfg.symbol)
        reason = "STOP-LOSS" if hit_sl else "TAKE-PROFIT"
        log(f"EXIT {state['side']} ({reason}) @ ~{price_now:.2f}")
        clear_state()


def try_enter(cfg, sig: dict):
    """Open a new trade if there is a signal and no open position."""
    if broker.get_position(cfg.symbol) is not None or load_state() is not None:
        return

    acc = broker.account()
    equity = float(acc.equity)

    # daily loss circuit breaker
    pnl = broker.pnl_today()
    if pnl <= -abs(equity * cfg.max_daily_loss_pct / 100.0):
        log(f"Daily loss limit hit ({pnl:+.2f}). No new trades today.")
        return

    if sig["long_entry"]:
        side, sl = "long", sig["price"] - cfg.atr_sl_mult * sig["atr"]
    elif sig["short_entry"]:
        side, sl = "short", sig["price"] + cfg.atr_sl_mult * sig["atr"]
    else:
        return

    stop_distance = abs(sig["price"] - sl)
    qty = int(risk.position_size(equity, cfg.risk_per_trade_pct, stop_distance,
                                 contract_size=1, min_lot=1,
                                 max_lot=1_000_000, lot_step=1))
    qty = min(qty, int(equity * 0.95 / sig["price"]))   # cap at no leverage
    if qty < 1:
        log("Signal skipped — position size rounds to 0 shares.")
        return

    order = broker.market_order(cfg.symbol, "buy" if side == "long" else "sell", qty)
    if order is not None:
        save_state({"side": side, "sl": sl, "tp": sig["bb_mid"],
                    "entry": sig["price"], "qty": qty})
        log(f"ENTER {side} {qty} {cfg.symbol} @ ~{sig['price']:.2f}  "
            f"SL {sl:.2f}  TP {sig['bb_mid']:.2f}")


def run():
    cfg = CONFIG
    if not broker.connect(cfg):
        log("Could not connect to Alpaca — check .env keys. Exiting.")
        return
    log(f"Bot started | {cfg.symbol} {cfg.timeframe} | PAPER trading | "
        f"risk {cfg.risk_per_trade_pct}%/trade | shorts={cfg.allow_shorts}")

    last_bar = None
    try:
        while True:
            df = broker.get_bars(cfg.symbol, cfg.timeframe, 320)
            if df is None or len(df) < cfg.ema_trend + 5:
                time.sleep(60)
                continue

            price_now = float(df["close"].iloc[-1])   # latest (forming) bar
            manage_position(cfg, price_now)            # check SL/TP every loop

            df_closed = df.iloc[:-1]                   # only act on closed bars
            bar_time = df_closed.index[-1]
            if bar_time != last_bar:
                last_bar = bar_time
                sig = strategy.signal(strategy.add_indicators(df_closed, cfg), cfg)
                log(f"New bar {bar_time:%Y-%m-%d %H:%M} | close {sig['price']:.2f} "
                    f"| long={sig['long_entry']} short={sig['short_entry']}")
                try_enter(cfg, sig)

            time.sleep(60)
    except KeyboardInterrupt:
        log("Stopped by user (Ctrl+C).")
    finally:
        broker.shutdown()


if __name__ == "__main__":
    run()
