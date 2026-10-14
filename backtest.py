"""
Backtest the strategy on historical 15-min data.

  python backtest.py                 # downloads ~5000 bars (~2.5 months) from Twelve Data
  python backtest.py --csv gold.csv  # longer history from your own CSV (recommended)

Trade management mirrors the live bot: half closed at TP1 with SL moved to
entry, the rest runs to TP2. If a bar touches both SL and a target, the SL is
assumed hit first (conservative). Spread is charged on every trade.
Note: the news blackout is NOT applied here (historical calendar not included).
"""
import argparse
import configparser
import os

import data
from strategy import prepare, evaluate

HERE = os.path.dirname(os.path.abspath(__file__))


SPLIT = True  # False when the position is the minimum lot and can't be halved


def simulate(d, i, sig):
    buy = sig["side"] == "BUY"
    sl, tp1_done = sig["sl"], False
    part = 0.5 if SPLIT else 0.0  # share of the position closed at TP1
    for j in range(i + 1, len(d)):
        hi, lo = d["high"].iloc[j], d["low"].iloc[j]
        if (lo <= sl) if buy else (hi >= sl):
            return (part * TP1_R if tp1_done else -1.0), j
        if not tp1_done and ((hi >= sig["tp1"]) if buy else (lo <= sig["tp1"])):
            tp1_done, sl = True, sig["entry"]
        if (hi >= sig["tp2"]) if buy else (lo <= sig["tp2"]):
            return part * TP1_R + (1 - part) * TP2_R, j
    return None, len(d)  # still open at end of data


def main():
    global TP1_R, TP2_R, SPLIT
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=os.path.join(HERE, "config.ini"))
    p.add_argument("--csv")
    p.add_argument("--no-split", action="store_true",
                   help="single minimum lot: no half-close at TP1, whole trade runs to TP2")
    args = p.parse_args()
    SPLIT = not args.no_split
    cfg = configparser.ConfigParser()
    cfg.read(args.config)
    s = cfg["strategy"]
    TP1_R, TP2_R, spread = float(s["tp1_r"]), float(s["tp2_r"]), float(s["spread"])

    df = data.load_csv(args.csv) if args.csv else data.fetch_twelvedata(
        cfg["data"]["twelvedata_api_key"], cfg["data"]["symbol"])
    d = prepare(df)
    print(f"Data: {d.index[0]:%Y-%m-%d} -> {d.index[-1]:%Y-%m-%d}, {len(d)} bars")

    trades, i = [], 1000  # warm-up for H1 EMA200
    while i < len(d):
        sig = evaluate(d, i, TP1_R, TP2_R)
        if sig:
            r, exit_i = simulate(d, i, sig)
            if r is None:
                break
            r -= spread / sig["sl_dist"]
            trades.append((sig["time"], sig["side"], r))
            i = exit_i + 1
        else:
            i += 1

    if not trades:
        print("No trades in this period.")
        return
    rs = [t[2] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    equity, peak, mdd = 0.0, 0.0, 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        mdd = max(mdd, peak - equity)
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")
    risk = float(cfg["account"]["risk_percent"])
    print(f"Trades:          {len(rs)}")
    print(f"Win rate:        {len(wins) / len(rs):.1%}")
    print(f"Avg per trade:   {sum(rs) / len(rs):+.2f} R")
    print(f"Total:           {sum(rs):+.1f} R  (~{sum(rs) * risk:+.1f}% at {risk}% risk)")
    print(f"Profit factor:   {pf:.2f}")
    print(f"Max drawdown:    {mdd:.1f} R  (~{mdd * risk:.1f}%)")
    print("\nLast 10 trades:")
    for t, side, r in trades[-10:]:
        print(f"  {t[:16]}  {side:4}  {r:+.2f} R")


if __name__ == "__main__":
    main()
