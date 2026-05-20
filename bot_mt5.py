"""Live trading bot — Bollinger mean-reversion on XAUUSD via MetaTrader 5.

WINDOWS ONLY (needs the MetaTrader5 package). Use a DEMO account first.
This is the MT5 variant — for the free macOS path use bot.py (Alpaca) instead.

    python bot_mt5.py

Stop with Ctrl+C. All activity is logged to logs/bot.log.
"""
import os
import time
from datetime import datetime, timezone

import mt5_connector as mt
import risk
import strategy
from config import CONFIG

os.makedirs("logs", exist_ok=True)


def log(msg: str):
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {msg}"
    print(line)
    with open("logs/bot.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def on_new_bar(cfg, sig: dict, start_balance: float):
    acc = mt.account_info()

    # 1. exit open positions when price reverts to the middle band
    for p in mt.get_positions(cfg.symbol, cfg.magic):
        if p.type == 0 and sig["exit_long"]:        # 0 = buy
            mt.close_position(p)
            log(f"EXIT long @ {sig['price']:.2f}")
        elif p.type == 1 and sig["exit_short"]:     # 1 = sell
            mt.close_position(p)
            log(f"EXIT short @ {sig['price']:.2f}")

    # 2. one position at a time
    if len(mt.get_positions(cfg.symbol, cfg.magic)) >= cfg.max_open_positions:
        return

    # 3. daily loss circuit breaker
    daily = mt.realized_pnl_today(cfg.magic)
    if daily <= -abs(start_balance * cfg.max_daily_loss_pct / 100.0):
        log(f"Daily loss limit reached ({daily:+.2f}). No new trades today.")
        return

    # 4. entries
    info = mt.symbol_info(cfg.symbol)
    if sig["long_entry"]:
        sl = sig["price"] - cfg.atr_sl_mult * sig["atr"]
        lots = risk.position_size(acc.balance, cfg.risk_per_trade_pct,
                                  sig["price"] - sl, info.trade_contract_size,
                                  info.volume_min, info.volume_max, info.volume_step)
        if lots > 0:
            mt.market_order(cfg.symbol, "buy", lots, sl, sig["bb_mid"], cfg.magic)
            log(f"BUY {lots} lots @ {sig['price']:.2f}  SL {sl:.2f}  TP {sig['bb_mid']:.2f}")
        else:
            log("Long signal skipped — safe size below broker minimum lot.")
    elif sig["short_entry"]:
        sl = sig["price"] + cfg.atr_sl_mult * sig["atr"]
        lots = risk.position_size(acc.balance, cfg.risk_per_trade_pct,
                                  sl - sig["price"], info.trade_contract_size,
                                  info.volume_min, info.volume_max, info.volume_step)
        if lots > 0:
            mt.market_order(cfg.symbol, "sell", lots, sl, sig["bb_mid"], cfg.magic)
            log(f"SELL {lots} lots @ {sig['price']:.2f}  SL {sl:.2f}  TP {sig['bb_mid']:.2f}")
        else:
            log("Short signal skipped — safe size below broker minimum lot.")


def run():
    cfg = CONFIG
    if not mt.connect(cfg):
        log("Could not connect to MT5 — check .env credentials. Exiting.")
        return

    acc = mt.account_info()
    start_balance = acc.balance
    log(f"Bot started | {cfg.symbol} {cfg.timeframe} | balance ${start_balance:,.2f} "
        f"| risk {cfg.risk_per_trade_pct}%/trade | shorts={cfg.allow_shorts}")

    last_bar = None
    try:
        while True:
            df = mt.get_rates(cfg.symbol, cfg.timeframe, 300)
            if df is None or len(df) < cfg.ema_trend + 5:
                time.sleep(30)
                continue

            df_closed = df.iloc[:-1]            # drop the still-forming bar
            bar_time = df_closed.index[-1]
            if bar_time == last_bar:
                time.sleep(20)
                continue
            last_bar = bar_time

            sig = strategy.signal(strategy.add_indicators(df_closed, cfg), cfg)
            on_new_bar(cfg, sig, start_balance)
    except KeyboardInterrupt:
        log("Stopped by user (Ctrl+C).")
    finally:
        mt.shutdown()


if __name__ == "__main__":
    run()
