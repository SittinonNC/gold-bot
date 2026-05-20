"""Backtest the Bollinger mean-reversion strategy on historical gold data.

Runs anywhere (uses yfinance, not MT5). Validate the strategy here BEFORE
ever running the live bot.

    python backtest.py                       # GC=F, 1 year, hourly
    python backtest.py --period 2y --interval 1d
"""
import argparse

import pandas as pd
import yfinance as yf

import strategy
from config import CONFIG


def load_data(symbol: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if df.empty:
        raise SystemExit(f"No data for {symbol} ({period}/{interval})")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    return df[["open", "high", "low", "close", "volume"]].dropna()


def run_backtest(cfg, df: pd.DataFrame, initial: float = 10000.0) -> dict:
    """Bar-by-bar simulation. Signal on the closed bar, act on the next open.

    Uses numpy arrays so it's fast enough to call hundreds of times (optimizer).
    """
    d = strategy.add_indicators(df, cfg).dropna().reset_index(drop=True)
    o, h, l, c = (d[x].to_numpy() for x in ("open", "high", "low", "close"))
    bb_l, bb_m, bb_u = (d[x].to_numpy() for x in ("bb_lower", "bb_mid", "bb_upper"))
    ema_t, rsi_v, atr_v = (d[x].to_numpy() for x in ("ema_trend", "rsi", "atr"))

    equity = initial
    eq_curve, trades = [], []
    pos = None

    for i in range(1, len(d)):
        # --- manage an open position (SL/TP checked intrabar) ---
        if pos:
            if pos["side"] == "long":
                hit_sl, hit_tp = l[i] <= pos["sl"], h[i] >= pos["tp"]
            else:
                hit_sl, hit_tp = h[i] >= pos["sl"], l[i] <= pos["tp"]
            exit_price = pos["sl"] if hit_sl else (pos["tp"] if hit_tp else None)
            if exit_price is not None:
                move = (exit_price - pos["entry"]) if pos["side"] == "long" else (pos["entry"] - exit_price)
                r = move / pos["risk"]                       # R-multiple
                equity += equity * cfg.risk_per_trade_pct / 100.0 * r
                trades.append(r)
                pos = None

        # --- look for a new entry (signal from the previous, closed bar) ---
        if pos is None:
            j = i - 1
            long_c = c[j] < bb_l[j] and c[j] > ema_t[j] and rsi_v[j] < cfg.rsi_oversold
            short_c = (cfg.allow_shorts and c[j] > bb_u[j] and c[j] < ema_t[j]
                       and rsi_v[j] > cfg.rsi_overbought)
            if long_c:
                entry = o[i]
                sl = entry - cfg.atr_sl_mult * atr_v[j]
                tp = bb_m[j]
                if sl < entry < tp:
                    pos = {"side": "long", "entry": entry, "sl": sl, "tp": tp, "risk": entry - sl}
            elif short_c:
                entry = o[i]
                sl = entry + cfg.atr_sl_mult * atr_v[j]
                tp = bb_m[j]
                if tp < entry < sl:
                    pos = {"side": "short", "entry": entry, "sl": sl, "tp": tp, "risk": sl - entry}

        eq_curve.append(equity)

    return {"initial": initial, "final": equity, "trades": trades,
            "eq_curve": eq_curve, "df": d}


def _max_drawdown(curve) -> float:
    if not curve:
        return 0.0
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd * 100.0


def print_report(s: dict):
    t = s["trades"]
    n = len(t)
    wins = [r for r in t if r > 0]
    gross_win = sum(r for r in t if r > 0)
    gross_loss = abs(sum(r for r in t if r < 0))
    bh = (s["df"]["close"].iloc[-1] / s["df"]["close"].iloc[0] - 1) * 100

    print("\n" + "=" * 48)
    print("  BOLLINGER MEAN-REVERSION — BACKTEST")
    print("=" * 48)
    print(f"  Bars analysed     : {len(s['df'])}")
    print(f"  Trades            : {n}")
    print(f"  Win rate          : {(len(wins) / n * 100) if n else 0:.1f}%")
    print(f"  Total return      : {(s['final'] / s['initial'] - 1) * 100:+.2f}%")
    print(f"  Buy & hold        : {bh:+.2f}%")
    print(f"  Max drawdown      : {_max_drawdown(s['eq_curve']):.2f}%")
    print(f"  Profit factor     : {(gross_win / gross_loss) if gross_loss else float('inf'):.2f}")
    print(f"  Avg R per trade   : {(sum(t) / n) if n else 0:+.2f}R")
    print(f"  Final equity      : ${s['final']:,.2f}  (from ${s['initial']:,.0f})")
    print("=" * 48)
    print("  Past performance does not guarantee future results.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="GC=F", help="Yahoo symbol (GC=F = gold futures)")
    ap.add_argument("--period", default="1y")
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--capital", type=float, default=10000.0)
    a = ap.parse_args()

    data = load_data(a.symbol, a.period, a.interval)
    print(f"Loaded {len(data)} bars of {a.symbol} ({a.period}/{a.interval})")
    print_report(run_backtest(CONFIG, data, a.capital))
