"""
Candle continuation strategy, run separately on each pair and timeframe.

  Order flow : candles closing beyond the previous candle. Bullish flow =
               at least 3 candles in a row (MIN_FLOW), each bullish and closing ABOVE
               the previous candle's high (bearish: each bearish and closing
               BELOW the previous candle's low).
  Reversal   : always wait for a pullback after the flow: 1-3 candles
               against it, none closing beyond the low (buys) / high (sells)
               of the last order-flow candle, or the flow is broken.
  Entry      : the next candle goes with the flow again: bullish and closes
               above the previous candle's high (sells: bearish, closes
               below the previous candle's low). Entry at its close.
  Stop       : below the low of the last order-flow candle (or the pullback
               low if lower) for buys; above the high for sells. Small
               buffer of 0.1*ATR. Never tighter than min_dist.
  TPs        : TP1 = 1.5R, TP2 = 3R (configurable).
  5m/1h filters: no entries 21:00-23:00 UTC (rollover) or late Friday.
  Confidence : High if the order flow ran 4+ candles, else Medium.
"""
import pandas as pd

from indicators import ema, rsi, atr, macd_hist

TF = {
    "5min": {"bar": pd.Timedelta("5min"), "freq": "5min", "higher": "1h", "label": "5M"},
    "1h": {"bar": pd.Timedelta("1h"), "freq": "1h", "higher": "4h", "label": "1H"},
    "1day": {"bar": pd.Timedelta("1D"), "freq": "1D", "higher": None, "label": "Daily"},
}


def prepare(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """df: OHLC with a UTC DatetimeIndex of bar OPEN times."""
    spec = TF[tf]
    d = df[["open", "high", "low", "close"]].copy()
    d.index.name = "datetime"
    d["ema20"] = ema(d["close"], 20)
    d["ema50"] = ema(d["close"], 50)
    d["ema200"] = ema(d["close"], 200)
    d["rsi"] = rsi(d["close"], 14)
    d["atr"] = atr(d, 14)
    d["macd_hist"] = macd_hist(d["close"])
    d["ct"] = d.index + spec["bar"]  # bar close time

    if spec["higher"]:
        rule = spec["higher"]
        r = (d[["open", "high", "low", "close"]].resample(rule)
             .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
             .dropna())
        r["hi_close"] = r["close"]
        r["hi_ema50"] = ema(r["close"], 50)
        r["ct"] = r.index + pd.Timedelta(rule)
        # only use higher-timeframe bars that had CLOSED (no look-ahead)
        d = (pd.merge_asof(d.reset_index().sort_values("ct"),
                           r[["ct", "hi_close", "hi_ema50"]].sort_values("ct"),
                           on="ct", direction="backward")
             .set_index("datetime"))
    else:
        d["hi_close"] = d["close"]
        d["hi_ema50"] = d["ema50"]
    return d


def _session_ok(tf, close_time: pd.Timestamp) -> bool:
    if tf == "1day":
        return True
    if close_time.hour in (21, 22):
        return False
    if close_time.weekday() == 4 and close_time.hour >= 19:
        return False
    return close_time.weekday() < 5


MIN_FLOW = 3       # order-flow candles needed before the pullback (change this number)
MAX_PULLBACK = 3   # most pullback candles allowed before the continuation


def _flow_up(d, k):
    """Candle k is bullish and closes above candle k-1's high."""
    return d["close"].iloc[k] > d["open"].iloc[k] and d["close"].iloc[k] > d["high"].iloc[k - 1]


def _flow_down(d, k):
    """Candle k is bearish and closes below candle k-1's low."""
    return d["close"].iloc[k] < d["open"].iloc[k] and d["close"].iloc[k] < d["low"].iloc[k - 1]


def _setup(d, i, buy):
    """For a continuation candle at i, find the pullback and the order flow
    before it. Returns (stop_level, flow_len) or None."""
    flow = _flow_up if buy else _flow_down
    if not flow(d, i):
        return None
    # pullback: 1-3 candles before i that go against the flow
    j = i - 1
    pull = []
    while j > 0 and len(pull) < MAX_PULLBACK:
        o, c = d["open"].iloc[j], d["close"].iloc[j]
        against = (c < o) if buy else (c > o)
        if not against:
            break
        pull.append(j)
        j -= 1
    if not pull:
        return None  # no reversal yet -> wait
    # order flow: candles ending at j, each closing beyond the one before
    k, n = j, 0
    while k > 0 and flow(d, k):
        n += 1
        k -= 1
    if n < MIN_FLOW:
        return None
    last_flow = j
    if buy:
        level = d["low"].iloc[last_flow]
        if min(d["close"].iloc[p] for p in pull) < level:
            return None  # pullback closed below the flow candle: flow broken
        level = min(level, min(d["low"].iloc[p] for p in pull))
    else:
        level = d["high"].iloc[last_flow]
        if max(d["close"].iloc[p] for p in pull) > level:
            return None
        level = max(level, max(d["high"].iloc[p] for p in pull))
    return float(level), n


def evaluate(d: pd.DataFrame, i: int, tf: str, tp1_r=1.5, tp2_r=3.0, decimals=2,
             min_dist=0.0):
    """Return a signal dict for bar i, or None.
    min_dist: smallest allowed stop distance (keeps 5-min stops wider than the spread)."""
    if i < 20:
        return None
    row = d.iloc[i]
    if pd.isna(row["atr"]) or not _session_ok(tf, row["ct"]):
        return None

    side, setup = None, _setup(d, i, True)
    if setup:
        side = "BUY"
    else:
        setup = _setup(d, i, False)
        if setup:
            side = "SELL"
    if side is None:
        return None

    level, flow_len = setup
    a = float(row["atr"])
    entry = float(row["close"])
    sgn = 1 if side == "BUY" else -1
    stop = level - sgn * 0.1 * a
    dist = (entry - stop) * sgn
    dist = float(max(dist, min_dist, 0.2 * a))
    r = lambda x: round(x, decimals)
    return {
        "side": side,
        "tf": tf,
        "time": row["ct"].isoformat(),
        "entry": r(entry),
        "sl": r(entry - sgn * dist),
        "tp1": r(entry + sgn * dist * tp1_r),
        "tp2": r(entry + sgn * dist * tp2_r),
        "sl_dist": dist,
        "confidence": "High" if flow_len >= MIN_FLOW + 1 else "Medium",
    }
