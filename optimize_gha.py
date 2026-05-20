"""Weekly re-optimizer for GitHub Actions.

Downloads fresh GLD data via yfinance, runs grid search with train/test split,
saves best params to params.json. The trading workflow reads this file each run
so the bot self-updates without any manual intervention.
"""
import json
import os
from copy import deepcopy
from datetime import date
from itertools import product

import yfinance as yf

from backtest import _max_drawdown, run_backtest
from config import CONFIG

PARAMS_FILE = "params.json"

GRID = {
    "bb_std":       [1.5, 2.0, 2.5, 3.0],
    "rsi_oversold": [25, 30, 35, 40],
    "atr_sl_mult":  [0.75, 1.0, 1.5, 2.0],
    "allow_shorts": [False, True],
}
MIN_TRADES_TRAIN = 10
MIN_TRADES_TEST  = 3


def _stats(s: dict) -> dict:
    t = s["trades"]
    n = len(t)
    wins = [r for r in t if r > 0]
    gross_win  = sum(r for r in t if r > 0)
    gross_loss = abs(sum(r for r in t if r < 0))
    return {
        "trades":        n,
        "win_rate":      round(len(wins) / n * 100, 1) if n else 0,
        "total_return":  round((s["final"] / s["initial"] - 1) * 100, 2),
        "max_drawdown":  round(_max_drawdown(s["eq_curve"]), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else 99.0,
    }


def load_current() -> dict | None:
    if os.path.exists(PARAMS_FILE):
        with open(PARAMS_FILE) as f:
            return json.load(f)
    return None


def run():
    print("=" * 56)
    print("  WEEKLY RE-OPTIMIZER")
    print("=" * 56)

    print("\nDownloading 1y GLD data (hourly)...")
    df = yf.download("GLD", period="1y", interval="1h",
                     auto_adjust=True, progress=False)
    if df.empty:
        print("No data — aborting.")
        return
    if hasattr(df.columns, "get_level_values"):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    print(f"Got {len(df)} bars  |  train/test split 70/30")

    split    = int(len(df) * 0.70)
    df_train = df.iloc[:split]
    df_test  = df.iloc[split:]

    cfg  = deepcopy(CONFIG)
    best_params = None
    best_score  = -999.0
    combos_tried = 0

    keys = list(GRID.keys())
    total = 1
    for v in GRID.values():
        total *= len(v)
    print(f"\nSearching {total} parameter combinations...")

    for combo in product(*GRID.values()):
        for k, v in zip(keys, combo):
            setattr(cfg, k, v)
        cfg.rsi_overbought = 100 - cfg.rsi_oversold

        s_train = _stats(run_backtest(cfg, df_train))
        if s_train["trades"] < MIN_TRADES_TRAIN:
            continue
        if s_train["profit_factor"] <= 1.0:
            continue

        s_test = _stats(run_backtest(cfg, df_test))
        if s_test["trades"] < MIN_TRADES_TEST:
            continue

        combos_tried += 1
        score = s_test["total_return"]  # rank by out-of-sample return
        if score > best_score:
            best_score = score
            best_params = {
                "bb_std":          cfg.bb_std,
                "rsi_oversold":    cfg.rsi_oversold,
                "rsi_overbought":  cfg.rsi_overbought,
                "atr_sl_mult":     cfg.atr_sl_mult,
                "allow_shorts":    cfg.allow_shorts,
                "train_return":    s_train["total_return"],
                "train_pf":        s_train["profit_factor"],
                "train_wr":        s_train["win_rate"],
                "test_return":     s_test["total_return"],
                "test_pf":         s_test["profit_factor"],
                "test_wr":         s_test["win_rate"],
                "updated":         str(date.today()),
            }

    print(f"Valid combinations: {combos_tried}/{total}")

    if best_params is None:
        print("\nNo valid params found — keeping current params unchanged.")
        return

    print(f"\nBest found:")
    print(f"  bb_std={best_params['bb_std']}  rsi_os={best_params['rsi_oversold']}  "
          f"atr_sl={best_params['atr_sl_mult']}  shorts={best_params['allow_shorts']}")
    print(f"  Train: return={best_params['train_return']:+.2f}%  PF={best_params['train_pf']}  "
          f"WR={best_params['train_wr']}%")
    print(f"  Test:  return={best_params['test_return']:+.2f}%  PF={best_params['test_pf']}  "
          f"WR={best_params['test_wr']}%")

    current = load_current()
    if current:
        print(f"\nCurrent params (from {current.get('updated', '?')}):")
        print(f"  test_return={current.get('test_return')}%  PF={current.get('test_pf')}")

    if current is None or best_params["test_return"] > current.get("test_return", -999):
        with open(PARAMS_FILE, "w") as f:
            json.dump(best_params, f, indent=2)
        print(f"\n✓ params.json updated! (was {current.get('test_return') if current else 'N/A'}% → now {best_params['test_return']}%)")
    else:
        print("\n— Current params still better — no update needed.")


if __name__ == "__main__":
    run()
