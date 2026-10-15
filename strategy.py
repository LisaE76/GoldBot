"""
Trend-following pullback strategy, run separately on each pair and timeframe.

  5min : trend = 1h close vs 1h EMA50 AND 5m EMA50 vs 5m EMA200
  1h   : trend = 4h close vs 4h EMA50 AND 1h EMA50 vs 1h EMA200
  1day : trend = daily close vs EMA50 AND daily EMA50 vs EMA200
  Entry: previous bar touched EMA20, current bar closes back on the trend
         side of EMA20 as a candle in the trend direction, RSI(14) 50-70
         for buys / 30-50 for sells.
  Stop : beyond the 5-bar swing +/- 0.3*ATR, kept between 1 and 3 ATR.
  TPs  : TP1 = 1.5R, TP2 = 3R (configurable).
  5m/1h filters: no entries 21:00-23:00 UTC (rollover) or late Friday.
  Confidence: High if MACD histogram agrees, else Medium.
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


def evaluate(d: pd.DataFrame, i: int, tf: str, tp1_r=1.5, tp2_r=3.0, decimals=2,
             min_dist=0.0):
    """Return a signal dict for bar i, or None.
    min_dist: smallest allowed stop distance (keeps 5-min stops wider than the spread)."""
    if i < 205:
        return None
    row, prev = d.iloc[i], d.iloc[i - 1]
    needed = ["ema20", "ema50", "ema200", "rsi", "atr", "hi_close", "hi_ema50"]
    if row[needed].isna().any() or pd.isna(prev["ema20"]):
        return None
    if not _session_ok(tf, row["ct"]):
        return None

    bull = row["hi_close"] > row["hi_ema50"] and row["ema50"] > row["ema200"]
    bear = row["hi_close"] < row["hi_ema50"] and row["ema50"] < row["ema200"]
    a = row["atr"]
    entry = float(row["close"])
    window = d.iloc[i - 4: i + 1]

    side = None
    if (bull and prev["low"] <= prev["ema20"] and row["close"] > row["ema20"]
            and row["close"] > row["open"] and 50 <= row["rsi"] <= 70):
        side = "BUY"
        dist = entry - (window["low"].min() - 0.3 * a)
    elif (bear and prev["high"] >= prev["ema20"] and row["close"] < row["ema20"]
            and row["close"] < row["open"] and 30 <= row["rsi"] <= 50):
        side = "SELL"
        dist = (window["high"].max() + 0.3 * a) - entry
    if side is None:
        return None

    dist = float(max(min(max(dist, 1.0 * a), 3.0 * a), min_dist))
    sgn = 1 if side == "BUY" else -1
    macd_agrees = (row["macd_hist"] > 0) if side == "BUY" else (row["macd_hist"] < 0)
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
        "confidence": "High" if macd_agrees else "Medium",
    }
