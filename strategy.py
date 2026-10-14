"""
Trend-following pullback strategy for XAUUSD.

Rules (evaluated on each completed 15-minute bar):
  Trend filter (multi-timeframe, completed bars only - no look-ahead):
    BUY  bias: H4 close > H4 EMA50  AND  H1 EMA50 > H1 EMA200
    SELL bias: H4 close < H4 EMA50  AND  H1 EMA50 < H1 EMA200
  Entry trigger on M15:
    BUY : previous bar dipped to/below EMA20, current bar closes back above
          EMA20 as a bullish candle, RSI(14) between 50 and 70
    SELL: mirror image, RSI between 30 and 50
  Stop loss: beyond the 5-bar swing +/- 0.3*ATR, clamped to 1-3 ATR
  Targets  : TP1 = 1.5R, TP2 = 3R (configurable)
  Filters  : no entries 21:00-23:00 UTC (rollover, thin liquidity)
             no entries after 19:00 UTC Friday (weekend gap risk)
  Confidence: High if MACD histogram agrees with direction, else Medium
"""
import pandas as pd

from indicators import ema, rsi, atr, macd_hist

M15 = pd.Timedelta("15min")


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """df: OHLC with a UTC DatetimeIndex of 15-min bar OPEN times."""
    d = df[["open", "high", "low", "close"]].copy()
    d.index.name = "datetime"
    d["ema20"] = ema(d["close"], 20)
    d["rsi"] = rsi(d["close"], 14)
    d["atr"] = atr(d, 14)
    d["macd_hist"] = macd_hist(d["close"])
    d["ct"] = d.index + M15  # bar close time

    for name, rule in (("h1", "1h"), ("h4", "4h")):
        r = (
            d[["open", "high", "low", "close"]]
            .resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
            .dropna()
        )
        r[f"{name}_close"] = r["close"]
        r[f"{name}_ema50"] = ema(r["close"], 50)
        r[f"{name}_ema200"] = ema(r["close"], 200)
        r["ct"] = r.index + pd.Timedelta(rule)
        cols = ["ct", f"{name}_close", f"{name}_ema50", f"{name}_ema200"]
        # attach the latest higher-timeframe bar that had CLOSED by this M15 close
        d = (
            pd.merge_asof(
                d.reset_index().sort_values("ct"),
                r[cols].sort_values("ct"),
                on="ct",
                direction="backward",
            )
            .set_index("datetime")
        )
    return d


def _session_ok(close_time: pd.Timestamp) -> bool:
    if close_time.hour in (21, 22):
        return False
    if close_time.weekday() == 4 and close_time.hour >= 19:
        return False
    if close_time.weekday() >= 5:
        return False
    return True


def evaluate(d: pd.DataFrame, i: int, tp1_r: float = 1.5, tp2_r: float = 3.0):
    """Return a signal dict for bar i, or None."""
    if i < 5:
        return None
    row, prev = d.iloc[i], d.iloc[i - 1]
    needed = ["ema20", "rsi", "atr", "h1_ema50", "h1_ema200", "h4_close", "h4_ema50"]
    if row[needed].isna().any() or pd.isna(prev["ema20"]):
        return None
    if not _session_ok(row["ct"]):
        return None

    bull = row["h4_close"] > row["h4_ema50"] and row["h1_ema50"] > row["h1_ema200"]
    bear = row["h4_close"] < row["h4_ema50"] and row["h1_ema50"] < row["h1_ema200"]
    a = row["atr"]
    entry = float(row["close"])
    window = d.iloc[i - 4 : i + 1]

    side = None
    if (
        bull
        and prev["low"] <= prev["ema20"]
        and row["close"] > row["ema20"]
        and row["close"] > row["open"]
        and 50 <= row["rsi"] <= 70
    ):
        side = "BUY"
        dist = entry - (window["low"].min() - 0.3 * a)
    elif (
        bear
        and prev["high"] >= prev["ema20"]
        and row["close"] < row["ema20"]
        and row["close"] < row["open"]
        and 30 <= row["rsi"] <= 50
    ):
        side = "SELL"
        dist = (window["high"].max() + 0.3 * a) - entry
    if side is None:
        return None

    dist = float(min(max(dist, 1.0 * a), 3.0 * a))
    sgn = 1 if side == "BUY" else -1
    macd_agrees = (row["macd_hist"] > 0) if side == "BUY" else (row["macd_hist"] < 0)
    return {
        "side": side,
        "time": row["ct"].isoformat(),
        "entry": round(entry, 2),
        "sl": round(entry - sgn * dist, 2),
        "tp1": round(entry + sgn * dist * tp1_r, 2),
        "tp2": round(entry + sgn * dist * tp2_r, 2),
        "sl_dist": round(dist, 2),
        "atr": round(float(a), 2),
        "rsi": round(float(row["rsi"]), 1),
        "confidence": "High" if macd_agrees else "Medium",
    }
