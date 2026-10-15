"""
Signal bot for XAUUSD, GBPUSD and EURUSD on the 5-minute, 1-hour and daily charts.

  python main.py --once            # check once (what GitHub runs)
  python main.py                   # run forever on a computer
  python main.py --test-sms        # send one test message and exit
"""
import argparse
import configparser
import json
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

import data
import news
from notifier import send_sms
from sizing import lot_size
from strategy import TF, prepare, evaluate

HERE = os.path.dirname(os.path.abspath(__file__))

# Environment variables (e.g. GitHub Secrets) override config.ini, so keys
# never have to be written into the files.
ENV_OVERRIDES = {
    "TWELVEDATA_API_KEY": ("data", "twelvedata_api_key"),
    "TWILIO_ACCOUNT_SID": ("sms", "account_sid"),
    "TWILIO_AUTH_TOKEN": ("sms", "auth_token"),
    "TWILIO_FROM": ("sms", "from_number"),
    "SMS_TO": ("sms", "to_numbers"),
    "TELEGRAM_BOT_TOKEN": ("sms", "telegram_bot_token"),
    "TELEGRAM_CHAT_ID": ("sms", "telegram_chat_id"),
    "ALERT_PROVIDER": ("sms", "provider"),
    "DRY_RUN": ("sms", "dry_run"),
    "ACCOUNT_BALANCE": ("account", "balance"),
}

# How old a signal may be and still be sent (GitHub runs can be late)
MAX_AGE = {"5min": timedelta(minutes=20), "1h": timedelta(hours=3),
           "1day": timedelta(hours=70)}
# How many bars of history to download per timeframe
OUTPUTSIZE = {"5min": 2000, "1h": 1500, "1day": 600}
FINEST = ["5min", "1h", "1day"]  # for following open trades
CCY = {"GBP": "£", "USD": "$", "EUR": "€"}


def load_cfg(path):
    cfg = configparser.ConfigParser()
    cfg.read(path)
    for env, (sec, key) in ENV_OVERRIDES.items():
        val = os.environ.get(env, "").strip()
        if val:
            cfg[sec][key] = val
    return cfg


def split(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def name(sym):
    return sym.replace("/", "")


def load_state(path):
    try:
        with open(path) as f:
            st = json.load(f)
    except Exception:
        st = {}
    if not isinstance(st.get("active"), dict) or "side" in (st.get("active") or {}):
        st["active"] = {}  # old single-pair format
    st.setdefault("last_eval", {})
    st.setdefault("last_fetch", {})
    st.setdefault("news_cache", None)
    st.setdefault("alerted_events", [])
    st.setdefault("last_heartbeat", None)
    return st


def save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, indent=2, default=str)


def fmt_local(t, tz, fmt="%a %H:%M"):
    return pd.Timestamp(t).tz_convert(tz).strftime(fmt)


def price_fmt(cfg, sym, x):
    return f"{x:.{int(cfg[sym]['decimals'])}f}"


def dist_fmt(cfg, sym, dist):
    if sym.startswith("XAU"):
        return f"${dist:.2f}"
    return f"{dist / float(cfg[sym]['pip']):.0f} pips"


def can_split(lots, cfg):
    """Half the position must still be at least the minimum lot."""
    return lots / 2 >= float(cfg["account"]["min_lot"]) - 1e-9


def pair_events(cfg, sym, events):
    ccys = set(split(cfg[sym].get("news_currencies", "USD")))
    return [e for e in events if e["currency"] in ccys]


def signal_message(cfg, tz, sym, sig, size, now, last_price, events, cal_err):
    a = cfg["account"]
    cur = CCY.get(a.get("account_currency", "USD").upper(), "")
    p = lambda x: price_fmt(cfg, sym, x)
    tp1_note = "close half, move SL to entry" if can_split(size["lots"], cfg) else "move SL to entry"
    lines = []
    if size["risk_pct"] >= 100:
        lines.append(f"!! TOO BIG FOR YOUR ACCOUNT: hitting the stop would lose "
                     f"{size['risk_pct']:.0f}% of your balance, even at the smallest lot")
    elif size["over_max"]:
        lines.append(f"!! HIGH RISK: {size['risk_pct']:.0f}% of account on one trade")
    lines += [
        f"{name(sym)} {sig['side']} · {TF[sig['tf']]['label']} ({sig['confidence']} confidence)",
        f"Entry: {p(sig['entry'])}",
        f"SL: {p(sig['sl'])} ({dist_fmt(cfg, sym, sig['sl_dist'])})",
        f"TP1: {p(sig['tp1'])} - {tp1_note}",
        f"TP2: {p(sig['tp2'])}",
        f"Lot: {size['lots']:.2f} (risk {cur}{size['risk']:,.2f} = {size['risk_pct']:.1f}% "
        f"of {cur}{float(a['balance']):,.0f})",
    ]
    if size["warning"] and not size["over_max"]:
        lines.append("! " + size["warning"])
    sig_t = pd.Timestamp(sig["time"])
    if now - sig_t.to_pydatetime() > timedelta(minutes=10):
        lines.append(f"Formed {fmt_local(sig_t, tz)}, price now {p(last_price)}")
    nxt = news.upcoming(pair_events(cfg, sym, events), now, 24)
    if nxt:
        e = nxt[0]
        lines.append(f"Next news: {e['currency']} {e['title']} {fmt_local(e['time'], tz)}")
    if cal_err:
        lines.append("! News calendar unavailable - check manually")
    lines.append("Not financial advice.")
    return "\n".join(lines)


def manage_active(cfg, state, key, track, msgs):
    """Follow an open signal on the given bars and report TP1 / TP2 / SL / expiry."""
    act = state["active"].get(key)
    if not act or track is None or track.empty:
        return
    sym = key.split("|")[0]
    p = lambda x: price_fmt(cfg, sym, x)
    tag = f"{name(sym)} {act['side']} {TF[act['tf']]['label']}"
    buy = act["side"] == "BUY"
    after = track[track["ct"] > pd.Timestamp(act["checked_to"])]
    for _, bar in after.iterrows():
        hi, lo = bar["high"], bar["low"]
        if (lo <= act["sl"]) if buy else (hi >= act["sl"]):
            what = "closed at breakeven" if act["tp1_done"] else "STOP LOSS hit"
            msgs.append(f"{tag} from {p(act['entry'])}: {what} ({p(act['sl'])}).")
            del state["active"][key]
            return
        if not act["tp1_done"] and ((hi >= act["tp1"]) if buy else (lo <= act["tp1"])):
            act["tp1_done"] = True
            act["sl"] = act["entry"]
            half = "Close half, move" if can_split(act.get("lots", 1), cfg) else "Move"
            msgs.append(f"{tag}: TP1 {p(act['tp1'])} hit. {half} SL to entry {p(act['entry'])}.")
        if (hi >= act["tp2"]) if buy else (lo <= act["tp2"]):
            msgs.append(f"{tag}: TP2 {p(act['tp2'])} hit. Trade complete.")
            del state["active"][key]
            return
        act["checked_to"] = bar["ct"].isoformat()
    hours = float(cfg["strategy"].get(f"expiry_hours_{act['tf']}", "48"))
    if track["ct"].iloc[-1] > pd.Timestamp(act["time"]) + timedelta(hours=hours):
        msgs.append(f"{tag} from {p(act['entry'])}: signal expired, manage manually "
                    f"(price {p(track['close'].iloc[-1])}).")
        del state["active"][key]


def get_events(cfg, state, now):
    """Economic calendar, refreshed at most once an hour (kept in state)."""
    n = cfg["news"]
    if not n.getboolean("enabled", fallback=True):
        return [], None
    cache = state.get("news_cache")
    if cache and now - datetime.fromisoformat(cache["fetched"]) < timedelta(minutes=60):
        evs = [{**e, "time": datetime.fromisoformat(e["time"])} for e in cache["events"]]
        return evs, cache.get("err")
    events, err = news.fetch_events(tuple(split(n["currencies"])), tuple(split(n["impacts"])))
    if err and cache:  # keep last good copy if the feed is down
        evs = [{**e, "time": datetime.fromisoformat(e["time"])} for e in cache["events"]]
        return evs, err
    state["news_cache"] = {"fetched": now.isoformat(), "err": err,
                           "events": [{**e, "time": e["time"].isoformat()} for e in events]}
    return events, err


def market_open(now):
    """Forex/gold trade from about Sunday 21:00 to Friday 22:00 UTC."""
    wd, h = now.weekday(), now.hour
    return not (wd == 5 or (wd == 6 and h < 21) or (wd == 4 and h >= 22))


def m5_window(cfg, now, tz):
    lo, hi = (int(x) for x in cfg["data"].get("m5_hours", "7-21").split("-"))
    local = pd.Timestamp(now).tz_convert(tz)
    return local.weekday() < 5 and lo <= local.hour < hi


def due(state, key, tf, now):
    """Fetch a chart only when a new bar has closed since the last fetch."""
    last = state["last_fetch"].get(key)
    if not last:
        return True
    f = TF[tf]["freq"]
    return pd.Timestamp(now).floor(f) > pd.Timestamp(last).floor(f)


def heartbeat(cfg, tz, state, now, last_prices, events, msgs):
    hour = int(cfg["general"].get("heartbeat_hour", "7"))
    local = pd.Timestamp(now).tz_convert(tz)
    today = local.strftime("%Y-%m-%d")
    if (hour < 0 or local.weekday() >= 5 or local.hour < hour
            or state["last_heartbeat"] == today or not last_prices):
        return
    state["last_heartbeat"] = today
    prices = " | ".join(f"{name(s)} {price_fmt(cfg, s, px)}" for s, px in last_prices.items())
    lines = [f"✅ Bot running - {local.strftime('%a %d %b')}", prices or "No prices (data error)"]
    if state["active"]:
        lines.append("Open signals:")
        for k, a in state["active"].items():
            s = k.split("|")[0]
            lines.append(f"  {name(s)} {a['side']} {TF[a['tf']]['label']} from {price_fmt(cfg, s, a['entry'])}")
    else:
        lines.append("Open signals: none")
    end = (local.normalize() + pd.Timedelta(days=1)).to_pydatetime()
    todays = [e for e in events if now <= e["time"] < end]
    if todays:
        lines.append("Today's big news:")
        lines += [f"  {fmt_local(e['time'], tz, '%H:%M')} {e['currency']} {e['title']}" for e in todays]
    else:
        lines.append("No big news today.")
    msgs.append("\n".join(lines))


def run_once(cfg, frames, now, state_path):
    """frames: {(symbol, tf): raw OHLC DataFrame}."""
    tz = ZoneInfo(cfg["general"].get("timezone", "UTC"))
    s, n, a = cfg["strategy"], cfg["news"], cfg["account"]
    state = load_state(state_path)
    msgs = []

    # --- news ---
    events, cal_err = get_events(cfg, state, now)
    if events:
        for ev in news.upcoming(events, now, hours=int(n["heads_up_min"]) / 60):
            key = f"{ev['currency']}|{ev['title']}|{ev['time'].isoformat()}"
            if key in state["alerted_events"]:
                continue
            state["alerted_events"] = (state["alerted_events"] + [key])[-100:]
            pairs = [name(sym) for sym in split(cfg["data"]["symbols"])
                     if ev["currency"] in split(cfg[sym].get("news_currencies", ""))]
            msgs.append(
                f"NEWS ALERT: {ev['currency']} {ev['title']} at {fmt_local(ev['time'], tz)} "
                f"(forecast {ev['forecast'] or '-'}, prev {ev['previous'] or '-'}). "
                f"Expect volatility on {', '.join(sorted(pairs)) or 'related pairs'}; "
                f"no new signals on those {n['blackout_before_min']}m before to "
                f"{n['blackout_after_min']}m after.")

    # --- prepare bars; the 1h bars are also used to follow open trades ---
    prepared, raw_closed, last_prices = {}, {}, {}
    for (sym, tf), df in frames.items():
        bar = TF[tf]["bar"]
        closed = data.drop_incomplete(df, bar, now)
        if len(closed) < 250:
            print(f"{name(sym)} {tf}: only {len(closed)} bars, skipping.")
            continue
        raw = closed.copy()
        raw["ct"] = raw.index + bar
        raw_closed[(sym, tf)] = raw
        prepared[(sym, tf)] = prepare(closed, tf)
        last_prices.setdefault(sym, {})[tf] = float(closed["close"].iloc[-1])
    last_prices = {sym: next(v[t] for t in FINEST if t in v) for sym, v in last_prices.items()}

    # --- follow open trades ---
    for key in list(state["active"]):
        sym = key.split("|")[0]
        tf = state["active"][key]["tf"]
        track = next((raw_closed[(sym, t)] for t in FINEST if (sym, t) in raw_closed), None)
        manage_active(cfg, state, key, track, msgs)

    # --- account currency rate (from GBP/USD data if we have it) ---
    acct = a.get("account_currency", "USD").upper()
    if acct == "USD":
        usd_per = 1.0
    elif f"{acct}/USD" in last_prices:
        usd_per = last_prices[f"{acct}/USD"]
        state["fx_rate"] = usd_per
    elif state.get("fx_rate"):
        usd_per = state["fx_rate"]
    else:
        usd_per = data.fetch_usd_per(acct, cfg["data"]["twelvedata_api_key"],
                                     a.get("fx_fallback", "1.0"))

    # --- new signals: check every bar closed since the last run ---
    for (sym, tf), d in prepared.items():
        key = f"{sym}|{tf}"
        last = state["last_eval"].get(key)
        oldest = pd.Timestamp(now) - MAX_AGE[tf]
        if last:
            oldest = max(oldest, pd.Timestamp(last) + pd.Timedelta(seconds=1))
        state["last_eval"][key] = d["ct"].iloc[-1].isoformat()
        sig = None
        for i in range(len(d) - 1, max(len(d) - 50, 0), -1):
            if d["ct"].iloc[i] < oldest:
                break
            min_dist = (float(s.get("min_stop_spreads", "4")) * float(cfg[sym]["spread"])
                        if tf == "5min" else 0.0)
            sig = evaluate(d, i, tf, float(s["tp1_r"]), float(s["tp2_r"]),
                           int(cfg[sym]["decimals"]), min_dist)
            if sig:
                break
        if not sig:
            continue
        label = f"{name(sym)} {sig['side']} {TF[tf]['label']}"
        block = news.blackout(pair_events(cfg, sym, events),
                              pd.Timestamp(sig["time"]).to_pydatetime(),
                              int(n["blackout_before_min"]), int(n["blackout_after_min"]))
        if block:
            print(f"{label} suppressed: news ({block['currency']} {block['title']}).")
            continue
        if key in state["active"]:
            print(f"{label} ignored: a {name(sym)} {TF[tf]['label']} signal is already open.")
            continue
        size = lot_size(float(a["balance"]), float(a["risk_percent"]), sig["sl_dist"],
                        float(cfg[sym]["contract_size"]), float(a["min_lot"]),
                        float(a["lot_step"]), float(a["max_lot"]), usd_per,
                        float(a.get("max_risk_percent", "100")))
        if size["over_max"] and a.getboolean("skip_over_max", fallback=False):
            print(f"{label} skipped: min lot risks {size['risk_pct']}% (> max_risk_percent).")
            continue
        msgs.append(signal_message(cfg, tz, sym, sig, size, now, last_prices[sym],
                                   events, cal_err))
        state["active"][key] = {**sig, "lots": size["lots"], "tp1_done": False,
                                "checked_to": sig["time"]}

    heartbeat(cfg, tz, state, now, last_prices, events, msgs)

    for m in msgs:
        send_sms(cfg, m)
    for (sym, tf), d in prepared.items():
        last = d.iloc[-1]
        print(f"[{now:%Y-%m-%d %H:%M} UTC] {name(sym):7} {TF[tf]['label']:5} "
              f"close {price_fmt(cfg, sym, last['close'])}  RSI {last['rsi']:.1f}  "
              f"open signal: {'yes' if f'{sym}|{tf}' in state['active'] else 'no'}")
    print(f"Messages sent: {len(msgs)}")
    # only mark charts as done once they've been fully checked
    state["last_fetch"].update({f"{sym}|{tf}": now.isoformat() for (sym, tf) in frames})
    save_state(state_path, state)


def fetch_all(cfg, state_path, now):
    """Download only the charts that have a newly closed bar."""
    tz = ZoneInfo(cfg["general"].get("timezone", "UTC"))
    if not market_open(now):
        print("Market closed - nothing to check.")
        return {}
    state = load_state(state_path)
    frames, fetched = {}, []
    for tf in split(cfg["data"]["timeframes"]):
        if tf == "5min" and not m5_window(cfg, now, tz):
            continue
        for sym in split(cfg["data"]["symbols"]):
            key = f"{sym}|{tf}"
            if not due(state, key, tf, now):
                continue
            try:
                frames[(sym, tf)] = data.fetch_twelvedata(
                    cfg["data"]["twelvedata_api_key"], sym, tf, OUTPUTSIZE.get(tf, 1000))
                fetched.append(key)
            except Exception as e:
                print(f"{name(sym)} {tf}: data error - {e}")
    print(f"Fetched: {', '.join(fetched) or 'nothing new'}")
    return frames


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=os.path.join(HERE, "config.ini"))
    p.add_argument("--once", action="store_true")
    p.add_argument("--test-sms", action="store_true", help="send one test message and exit")
    args = p.parse_args()
    cfg = load_cfg(args.config)
    if args.test_sms:
        ok = send_sms(cfg, "Signal bot connected ✅ You'll get XAUUSD, GBPUSD and EURUSD "
                           "signals (5M, 1H and Daily) and news alerts here. Not financial advice.")
        print("Test message sent." if ok else
              "Test message FAILED - check your Telegram bot token and chat ID.")
        raise SystemExit(0 if ok else 1)
    state_path = os.path.join(HERE, cfg["general"].get("state_file", "state.json"))
    interval = int(cfg["general"].get("check_interval_min", 30))

    while True:
        now = datetime.now(timezone.utc)
        try:
            frames = fetch_all(cfg, state_path, now)
            if frames:
                run_once(cfg, frames, now, state_path)
        except Exception as e:
            print("Error:", e)
        if args.once:
            break
        time.sleep(interval * 60)


if __name__ == "__main__":
    main()
