"""Price data: Twelve Data API (live) or a CSV file (offline/backtests)."""
from datetime import datetime, timezone

import pandas as pd
import requests

M15 = pd.Timedelta("15min")


def fetch_twelvedata(api_key, symbol="XAU/USD", interval="15min", outputsize=5000):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={"symbol": symbol, "interval": interval, "outputsize": outputsize,
                "timezone": "UTC", "apikey": api_key, "order": "ASC"},
        timeout=30,
    )
    j = r.json()
    if j.get("status") == "error" or "values" not in j:
        raise RuntimeError(f"Twelve Data error: {j.get('message', j)}")
    df = pd.DataFrame(j["values"])
    return _clean(df)


def fetch_usd_per(currency, api_key, fallback):
    """USD value of 1 unit of the account currency (e.g. GBP -> ~1.3)."""
    if currency.upper() == "USD":
        return 1.0
    try:
        r = requests.get("https://api.twelvedata.com/price",
                         params={"symbol": f"{currency.upper()}/USD", "apikey": api_key},
                         timeout=15)
        return float(r.json()["price"])
    except Exception:
        return float(fallback)


def load_csv(path):
    """CSV with columns: datetime,open,high,low,close (UTC, 15-min bar open times)."""
    return _clean(pd.read_csv(path))


def _clean(df):
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime").sort_index()
    df = df[["open", "high", "low", "close"]].astype(float)
    df = df[~df.index.duplicated(keep="last")]
    return df


def drop_incomplete(df, now=None):
    """Remove the last bar if it hasn't closed yet."""
    now = now or datetime.now(timezone.utc)
    if len(df) and df.index[-1] + M15 > now:
        return df.iloc[:-1]
    return df
