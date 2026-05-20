# 🥇 Gold Bot — Bollinger Mean-Reversion

Automated trading bot for gold. Strategy: **Bollinger Band mean-reversion**
with an EMA200 trend filter — buy dips below the lower band in an uptrend
(and sell rips above the upper band in a downtrend), take profit when price
reverts to the middle band.

> ⚠️ **Educational use. Not financial advice. Paper money only to start.**
> Trade real money only after the bot has proven itself for 1–3 months.

## Two ways to run

| Path | Broker | Cost | Runs on | Bot file |
|------|--------|------|---------|----------|
| **Alpaca (recommended)** | Alpaca paper | **Free** | macOS / anywhere | `bot.py` |
| MetaTrader 5 | MT5 demo | Free*, needs Windows | Windows only | `bot_mt5.py` |

\* MT5 itself is free but the `MetaTrader5` Python package is Windows-only, so
that path needs a Windows PC or a paid Windows VPS. **Start with Alpaca.**

The Alpaca path trades the **GLD** ETF (price tracks gold). It trades during
US market hours only (~6.5 h/day) — fine for learning.

## Files

| File | Role |
|------|------|
| `config.py` | All settings (loaded from `.env`) |
| `strategy.py` | Indicators + Bollinger signal logic |
| `risk.py` | Position sizing (risk % per trade) |
| `backtest.py` | Historical backtest (yfinance data) |
| `optimize.py` | Parameter tuning with train/test split |
| `alpaca_connector.py` | Alpaca data + orders |
| `bot.py` | Live paper-trading bot (Alpaca) |
| `mt5_connector.py` / `bot_mt5.py` | MetaTrader 5 path (Windows) |

## Setup (Alpaca — free, on your Mac)

```bash
cd gold-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

1. Sign up free at <https://alpaca.markets>.
2. Switch to **Paper Trading**, open **API Keys**, generate a key + secret.
3. Copy `.env.example` to `.env` and paste in `ALPACA_KEY` / `ALPACA_SECRET`.
4. Run it:

```bash
python backtest.py        # validate the strategy first
python optimize.py        # (optional) re-tune the parameters
python bot.py             # start the paper-trading bot
```

The bot logs to `logs/bot.log` and remembers the open trade in
`logs/state.json`. Stop with `Ctrl+C`. It only places trades during US
market hours — outside those hours it just waits.

## Strategy rules (current, tuned settings)

- **Long entry:** close < lower Bollinger band, close > EMA200, RSI < 40
- **Short entry:** close > upper band, close < EMA200, RSI > 60
- **Bollinger:** period 20, **2.5** standard deviations
- **Stop loss:** 1.0 × ATR from entry
- **Take profit:** middle Bollinger band (SMA20)
- **Risk:** 1% of equity per trade; bot stops for the day after a 3% loss
- **One position at a time**

Edit anything in `config.py` / `.env`, then re-run `backtest.py`.

## Safety checklist before real money

- [ ] Backtest + optimize results reviewed and understood
- [ ] Ran on the Alpaca paper account for at least 1–3 months
- [ ] `RISK_PER_TRADE_PCT` / `MAX_DAILY_LOSS_PCT` set conservatively
- [ ] You can afford to lose every dollar in the account
