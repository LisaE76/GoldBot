"""
Backtest the strategy on one pair and timeframe.

  python backtest.py --symbol XAU/USD --tf 5min
  python backtest.py --symbol XAU/USD --tf 1h
  python backtest.py --symbol GBP/USD --tf 1day
  python backtest.py --symbol EUR/USD --tf 1h --csv eurusd_1h.csv
  python backtest.py --all                    # every pair and timeframe

Half closed at TP1 with SL moved to entry, the rest runs to TP2 (--no-split:
a single minimum lot that can't be halved, so the whole trade runs to TP2).
If a bar touches both SL and a target, the SL is assumed hit first.
Spread is charged on every trade. The news filter is NOT applied here.
"""
import argparse
import os
import time

import data
from main import load_cfg, split, name, OUTPUTSIZE
from strategy import TF, prepare, evaluate

HERE = os.path.dirname(os.path.abspath(__file__))


def simulate(d, i, sig, tp1_r, tp2_r, split_pos):
    buy = sig["side"] == "BUY"
    sl, tp1_done = sig["sl"], False
    part = 0.5 if split_pos else 0.0
    for j in range(i + 1, len(d)):
        hi, lo = d["high"].iloc[j], d["low"].iloc[j]
        if (lo <= sl) if buy else (hi >= sl):
            return (part * tp1_r if tp1_done else -1.0), j
        if not tp1_done and ((hi >= sig["tp1"]) if buy else (lo <= sig["tp1"])):
            tp1_done, sl = True, sig["entry"]
        if (hi >= sig["tp2"]) if buy else (lo <= sig["tp2"]):
            return part * tp1_r + (1 - part) * tp2_r, j
    return None, len(d)


def backtest(cfg, df, sym, tf, split_pos=True):
    s = cfg["strategy"]
    tp1_r, tp2_r = float(s["tp1_r"]), float(s["tp2_r"])
    spread = float(cfg[sym]["spread"])
    d = prepare(df, tf)
    trades, i = [], 250
    while i < len(d):
        min_dist = float(s.get("min_stop_spreads", "4")) * spread if tf == "5min" else 0.0
        sig = evaluate(d, i, tf, tp1_r, tp2_r, int(cfg[sym]["decimals"]), min_dist)
        if sig:
            r, exit_i = simulate(d, i, sig, tp1_r, tp2_r, split_pos)
            if r is None:
                break
            trades.append((sig["time"], sig["side"], r - spread / sig["sl_dist"]))
            i = exit_i + 1
        else:
            i += 1
    return d, trades


def report(cfg, sym, tf, d, trades):
    print(f"\n=== {name(sym)} {TF[tf]['label']}  "
          f"({d.index[0]:%Y-%m-%d} -> {d.index[-1]:%Y-%m-%d}, {len(d)} bars) ===")
    if not trades:
        print("No trades in this period.")
        return
    rs = [t[2] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    eq = peak = mdd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        mdd = max(mdd, peak - eq)
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else float("inf")
    risk = float(cfg["account"]["risk_percent"])
    print(f"Trades: {len(rs)}   Win rate: {len(wins) / len(rs):.0%}   "
          f"Avg: {sum(rs) / len(rs):+.2f}R   Total: {sum(rs):+.1f}R   "
          f"Profit factor: {pf:.2f}   Max drawdown: {mdd:.1f}R (~{mdd * risk:.0f}% at {risk}%)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=os.path.join(HERE, "config.ini"))
    p.add_argument("--symbol", default="XAU/USD")
    p.add_argument("--tf", default="1h", choices=list(TF))
    p.add_argument("--csv", help="your own history: datetime,open,high,low,close (UTC)")
    p.add_argument("--all", action="store_true", help="every pair and timeframe in config")
    p.add_argument("--no-split", action="store_true")
    args = p.parse_args()
    cfg = load_cfg(args.config)
    jobs = ([(s, t) for s in split(cfg["data"]["symbols"]) for t in split(cfg["data"]["timeframes"])]
            if args.all else [(args.symbol, args.tf)])
    for n, (sym, tf) in enumerate(jobs):
        if args.csv and not args.all:
            df = data.load_csv(args.csv)
        else:
            if n and n % 7 == 0:
                time.sleep(61)  # free data plan: 8 requests a minute
            df = data.fetch_twelvedata(cfg["data"]["twelvedata_api_key"], sym, tf, 5000)
        d, trades = backtest(cfg, df, sym, tf, not args.no_split)
        report(cfg, sym, tf, d, trades)


if __name__ == "__main__":
    main()
