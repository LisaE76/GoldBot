# XAUUSD Signal Bot

Watches gold (XAU/USD) on the 15-minute chart, checks the economic calendar,
and texts you BUY/SELL signals with entry, stop loss, two take-profits and a
lot size matched to your account. It then follows each trade and texts you
when TP1, TP2 or the stop is hit.

> **Read this first.** No software can accurately predict gold. This bot
> follows fixed rules (trend + pullback) and manages risk. It *will* have
> losing streaks. Run the backtest on real data and paper-trade it before
> risking money. Nothing here is financial advice.

## What it does

| Feature | How |
|---|---|
| Trend direction | H4 price vs EMA50 and H1 EMA50 vs EMA200 must agree |
| Entry | M15 pullback to EMA20, then a candle closing back in trend direction, RSI confirming |
| Stop loss | Beyond the recent 5-bar swing, kept between 1x and 3x ATR |
| Take profit | TP1 = 1.5R (close half, stop to breakeven), TP2 = 3R |
| News | ForexFactory calendar: no new signals 30 min before/after high-impact USD events (CPI, NFP, FOMC...) and an SMS heads-up before each |
| Sessions | No entries during rollover (21:00-23:00 UTC) or late Friday |
| Lot size | `lots = (balance x risk%) / (stop distance $ x 100 oz)`, rounded down to 0.01 |
| SMS | Twilio, to one or more numbers (WhatsApp also supported) |

Example text:
```
XAUUSD BUY (High confidence)
Entry: 2710.87
SL: 2699.52 ($11.35)
TP1: 2727.89 - close half, move SL to entry
TP2: 2744.91
Lot: 0.08 (risk $90.80 on $10,000)
Next news: USD CPI y/y Wed 13:30
Not financial advice.
```

## Setup (about 15 minutes)

1. **Install Python 3.9+**, then in this folder:
   ```
   pip install -r requirements.txt
   ```
2. **Price data key:** sign up free at twelvedata.com, copy your API key into
   `config.ini` -> `twelvedata_api_key`.
3. **SMS:** sign up at twilio.com. Copy the Account SID, Auth Token and your
   Twilio phone number into `config.ini` `[sms]`. Put your mobile in
   `to_numbers` in international format (e.g. `+447700900000`).
   On a Twilio trial you must first verify your own number in their console.
4. **Your account:** pre-set to £52 (GBP), 0.01 minimum lot. Change
   `balance` in `[account]` as your account grows. Check your broker's
   contract size for XAUUSD (most use 100 oz per lot, so 0.01 lot = $1 per
   $1 move). The GBP/USD rate is fetched live for the risk figures.

   **Small accounts:** at 0.01 lot, a typical $10-20 gold stop risks
   roughly £7-15, which is 15-30% of £52. Signals above `max_risk_percent`
   (10%) are flagged HIGH RISK; set `skip_over_max = true` to drop them.
   A 0.01 lot can't be halved, so at TP1 the text says to move the stop to
   entry and let the whole trade run to TP2. Backtest that style with
   `python backtest.py --no-split`.
5. **Test:** keep `dry_run = true` and run
   ```
   python main.py --once
   ```
   Messages print to the screen instead of being sent.
6. **Go live:** set `dry_run = false`.

## Running it

Run continuously (checks every 15 minutes):
```
python main.py
```
Or schedule `python main.py --once` every 15 minutes with cron (Linux/Mac)
or Task Scheduler (Windows). For 24/5 alerts, run it on an always-on machine
or a cheap VPS.

## Backtesting (do this before trusting it)

```
python backtest.py                 # last ~2.5 months from Twelve Data
python backtest.py --csv gold.csv  # your own longer history (better)
```
CSV columns: `datetime,open,high,low,close` (UTC, 15-minute bars). Most
brokers' MT4/MT5 history centres can export this. Look at win rate, profit
factor (>1.3 is reasonable), and max drawdown. Test at least a year of data.

## Files

- `config.ini` - all settings
- `main.py` - the bot
- `strategy.py` - entry/exit rules (edit here to change the strategy)
- `news.py` - economic calendar filter
- `sizing.py` - lot size calculation
- `notifier.py` - SMS sending
- `data.py` - price data
- `backtest.py` - historical test
- `state.json` - created automatically; remembers the active trade

## Limits to know

- Only scheduled calendar events are covered. Surprise headlines (wars,
  central-bank comments) aren't detected; a sudden spike can still hit stops.
- Entry is the 15-min close price; your fill will differ by spread/slippage.
- Account currency is assumed to be USD.
- The free Twelve Data plan gives ~5,000 bars, enough for live use.
