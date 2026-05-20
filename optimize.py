"""Grid-search the strategy parameters — the HONEST way.

Tunes on the first 70% of history (in-sample / "train"), then verifies the
best setting on the last 30% the optimizer never saw (out-of-sample / "test").
If a setting looks great on train but collapses on test, it is OVERFIT and
must not be trusted.

    python optimize.py
"""
import dataclasses
import itertools

import backtest
from config import CONFIG

# Parameter values to try. More values = slower but more thorough.
GRID = {
    "bb_std": [1.5, 2.0, 2.5],
    "rsi_oversold": [25, 30, 35, 40],
    "atr_sl_mult": [1.0, 1.5, 2.0, 2.5],
    "allow_shorts": [False, True],
}
MIN_TRADES = 10   # ignore settings with too few trades to be meaningful


def stats(s: dict) -> dict | None:
    t = s["trades"]
    n = len(t)
    if n == 0:
        return None
    gw = sum(r for r in t if r > 0)
    gl = abs(sum(r for r in t if r < 0))
    return {
        "trades": n,
        "win_rate": sum(1 for r in t if r > 0) / n * 100,
        "return": (s["final"] / s["initial"] - 1) * 100,
        "max_dd": backtest._max_drawdown(s["eq_curve"]),
        "pf": (gw / gl) if gl else float("inf"),
    }


def main():
    full = backtest.load_data("GC=F", "730d", "1h")
    split = int(len(full) * 0.7)
    train, test = full.iloc[:split], full.iloc[split:]
    print(f"Data: {len(full)} bars   train={len(train)}   test={len(test)}")
    print(f"Testing {len(list(itertools.product(*GRID.values())))} parameter combinations...\n")

    keys = list(GRID)
    rows = []
    for combo in itertools.product(*GRID.values()):
        p = dict(zip(keys, combo))
        cfg = dataclasses.replace(CONFIG, rsi_overbought=100 - p["rsi_oversold"], **p)
        st = stats(backtest.run_backtest(cfg, train))
        if st and st["trades"] >= MIN_TRADES and st["pf"] > 1.0:
            rows.append((p, cfg, st))

    rows.sort(key=lambda r: r[2]["return"], reverse=True)
    if not rows:
        print("No parameter set met the criteria (>=10 trades, profit factor > 1).")
        return

    print("TOP 8 IN-SAMPLE (train) SETTINGS")
    print("-" * 76)
    hdr = ("bb_std", "rsi_os", "atr_sl", "shorts", "trades", "win%", "return%", "maxDD%", "PF")
    print("".join(f"{h:>9}" for h in hdr))
    for p, _, st in rows[:8]:
        print(f"{p['bb_std']:>9}{p['rsi_oversold']:>9}{p['atr_sl_mult']:>9}"
              f"{str(p['allow_shorts']):>9}{st['trades']:>9}{st['win_rate']:>9.1f}"
              f"{st['return']:>9.2f}{st['max_dd']:>9.2f}{st['pf']:>9.2f}")

    # --- the honest part: verify the winner on unseen data ---
    best_p, best_cfg, best_train = rows[0]
    best_test = stats(backtest.run_backtest(best_cfg, test))

    print("\n" + "=" * 60)
    print("BEST SETTING  —  OUT-OF-SAMPLE CHECK (the honest test)")
    print("=" * 60)
    print(f"  Params: {best_p}\n")
    print(f"  {'metric':<16}{'train (seen)':>16}{'test (unseen)':>16}")
    for key, label in [("return", "Return %"), ("win_rate", "Win rate %"),
                       ("max_dd", "Max drawdown %"), ("pf", "Profit factor"),
                       ("trades", "Trades")]:
        tv = best_train[key]
        ev = best_test[key] if best_test else 0.0
        print(f"  {label:<16}{tv:>16.2f}{ev:>16.2f}")
    print("=" * 60)
    if best_test and best_test["return"] > 0 and best_test["pf"] > 1.0:
        print("  VERDICT: holds up on unseen data — a reasonable, robust setting.")
    else:
        print("  VERDICT: collapses on unseen data — OVERFIT. Do not trust it.")
    print("  Past performance does not guarantee future results.")


if __name__ == "__main__":
    main()
