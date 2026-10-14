"""
XAUUSD signal bot.

  python main.py --once            # check once (ideal for cron / Task Scheduler)
  python main.py                   # run forever, checking every 15 minutes
  python main.py --once --csv f.csv --now 2026-10-14T13:30Z   # offline test
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
from strategy import prepare, evaluate

HERE = os.path.dirname(os.path.abspath(__file__))


# Environment variables (e.g. GitHub Secrets) override config.ini, so keys
# never have to be written into the files.
ENV_OVERRIDES = {
    "TWELVEDATA_API_KEY": ("data", "twelvedata_api_key"),
    "TWILIO_ACCOUNT_SID": ("sms", "account_sid"),
    "TWILIO_AUTH_TOKEN": ("sms", "auth_token"),
    "TWILIO_FROM": ("sms", "from_number"),
    "SMS_TO": ("sms", "to_numbers"),
    "DRY_RUN": ("sms", "dry_run"),
    "ACCOUNT_BALANCE": ("account", "balance"),
}


def load_cfg(path):
    cfg = configparser.ConfigParser()
    cfg.read(path)
    for env, (sec, key) in ENV_OVERRIDES.items():
        val = os.environ.get(env, "").strip()
        if val:
            cfg[sec][key] = val
    return cfg


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"active": None, "last_signal_time": None, "alerted_events": []}


def save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, indent=2, default=str)


def fmt_local(t, tz):
    return t.astimezone(tz).strftime("%a %H:%M")


CCY = {"GBP": "£", "USD": "$", "EUR": "€"}


def can_split(lots, cfg):
    """Half the position must still be at least the minimum lot."""
    a = cfg["account"]
    return lots / 2 >= float(a["min_lot"]) - 1e-9


def signal_message(sig, cfg, tz, size, next_events, cal_err):
    a = cfg["account"]
    cur = CCY.get(a.get("account_currency", "USD").upper(), "")
    lots = size["lots"]
    tp1_note = "close half, move SL to entry" if can_split(lots, cfg) else "move SL to entry"
    lines = []
    if size["over_max"]:
        lines.append(f"!! HIGH RISK: {size['risk_pct']:.0f}% of account on one trade")
    lines += [
        f"XAUUSD {sig['side']} ({sig['confidence']} confidence)",
        f"Entry: {sig['entry']:.2f}",
        f"SL: {sig['sl']:.2f} (${sig['sl_dist']:.2f})",
        f"TP1: {sig['tp1']:.2f} - {tp1_note}",
        f"TP2: {sig['tp2']:.2f}",
        f"Lot: {lots:.2f} (risk {cur}{size['risk']:,.2f} = {size['risk_pct']:.1f}% "
        f"of {cur}{float(a['balance']):,.0f})",
    ]
    if size["warning"] and not size["over_max"]:
        lines.append("! " + size["warning"])
    if next_events:
        e = next_events[0]
        lines.append(f"Next news: {e['currency']} {e['title']} {fmt_local(e['time'], tz)}")
    if cal_err:
        lines.append("! News calendar unavailable - check manually")
    lines.append("Not financial advice.")
    return "\n".join(lines)


def manage_active(state, d, cfg, msgs):
    """Track an open signal and report TP1 / TP2 / SL / expiry."""
    act = state["active"]
    if not act:
        return
    after = d[d["ct"] > pd.Timestamp(act["checked_to"])]
    buy = act["side"] == "BUY"
    for _, bar in after.iterrows():
        hi, lo = bar["high"], bar["low"]
        stop_hit = lo <= act["sl"] if buy else hi >= act["sl"]
        tp1_hit = hi >= act["tp1"] if buy else lo <= act["tp1"]
        tp2_hit = hi >= act["tp2"] if buy else lo <= act["tp2"]
        if stop_hit:  # checked first: conservative when a bar spans both
            what = "closed at breakeven" if act["tp1_done"] else "STOP LOSS hit"
            msgs.append(f"XAUUSD {act['side']} from {act['entry']:.2f}: {what} ({act['sl']:.2f}).")
            state["active"] = None
            return
        if not act["tp1_done"] and tp1_hit:
            act["tp1_done"] = True
            act["sl"] = act["entry"]
            half = "Close half, move" if can_split(act.get("lots", 1), cfg) else "Move"
            msgs.append(f"XAUUSD {act['side']}: TP1 {act['tp1']:.2f} hit. "
                        f"{half} SL to entry {act['entry']:.2f}.")
        if tp2_hit:
            msgs.append(f"XAUUSD {act['side']}: TP2 {act['tp2']:.2f} hit. Trade complete.")
            state["active"] = None
            return
        act["checked_to"] = bar["ct"].isoformat()
    expiry = pd.Timestamp(act["time"]) + timedelta(hours=float(cfg["strategy"]["signal_expiry_hours"]))
    if len(d) and d["ct"].iloc[-1] > expiry:
        msgs.append(f"XAUUSD {act['side']} from {act['entry']:.2f}: signal expired, "
                    f"manage manually (price {d['close'].iloc[-1]:.2f}).")
        state["active"] = None


def run_once(cfg, df, now, state_path):
    tz = ZoneInfo(cfg["general"].get("timezone", "UTC"))
    s, n, a = cfg["strategy"], cfg["news"], cfg["account"]
    state = load_state(state_path)
    msgs = []

    d = prepare(data.drop_incomplete(df, now))
    if len(d) < 1000:
        print(f"Only {len(d)} bars - need ~1000+ for the H1 EMA200. Skipping.")
        return

    manage_active(state, d, cfg, msgs)

    # --- news ---
    events, cal_err, block = [], None, None
    if n.getboolean("enabled", fallback=True):
        events, cal_err = news.fetch_events(
            tuple(x.strip() for x in n["currencies"].split(",")),
            tuple(x.strip() for x in n["impacts"].split(",")),
        )
        block = news.blackout(events, now, int(n["blackout_before_min"]), int(n["blackout_after_min"]))
        for ev in news.upcoming(events, now, hours=int(n["heads_up_min"]) / 60):
            key = f"{ev['title']}|{ev['time'].isoformat()}"
            if key not in state["alerted_events"]:
                state["alerted_events"] = (state["alerted_events"] + [key])[-50:]
                msgs.append(
                    f"NEWS ALERT: {ev['currency']} {ev['title']} at {fmt_local(ev['time'], tz)} "
                    f"(forecast {ev['forecast'] or '-'}, prev {ev['previous'] or '-'}). "
                    f"Expect XAUUSD volatility; no new signals "
                    f"{n['blackout_before_min']}m before to {n['blackout_after_min']}m after."
                )

    # --- new signal ---
    # Check the last two closed bars, so a run that starts a few minutes late
    # (common on scheduled cloud runners) doesn't miss a signal; ignore stale ones.
    sig = None
    for i in (len(d) - 1, len(d) - 2):
        cand = evaluate(d, i, float(s["tp1_r"]), float(s["tp2_r"]))
        if cand and now - pd.Timestamp(cand["time"]).to_pydatetime() <= timedelta(minutes=35):
            sig = cand
            break
    if sig and sig["time"] != state["last_signal_time"]:
        state["last_signal_time"] = sig["time"]
        if block:
            print(f"Signal {sig['side']} suppressed: news blackout ({block['title']}).")
        elif state["active"]:
            print(f"Signal {sig['side']} ignored: a signal is already active.")
        else:
            usd_per = data.fetch_usd_per(
                a.get("account_currency", "USD"), cfg["data"]["twelvedata_api_key"],
                a.get("fx_fallback", "1.0"))
            size = lot_size(
                float(a["balance"]), float(a["risk_percent"]), sig["sl_dist"],
                float(a["contract_size"]), float(a["min_lot"]), float(a["lot_step"]),
                float(a["max_lot"]), usd_per, float(a.get("max_risk_percent", "100")),
            )
            if size["over_max"] and a.getboolean("skip_over_max", fallback=False):
                print(f"Signal {sig['side']} skipped: min lot risks {size['risk_pct']}% "
                      f"(> max_risk_percent).")
            else:
                msgs.append(signal_message(sig, cfg, tz, size,
                                           news.upcoming(events, now, 24), cal_err))
                state["active"] = {**sig, "lots": size["lots"], "tp1_done": False,
                                   "checked_to": sig["time"]}

    for m in msgs:
        send_sms(cfg, m)
    last = d.iloc[-1]
    print(f"[{now:%Y-%m-%d %H:%M} UTC] price {last['close']:.2f}  RSI {last['rsi']:.1f}  "
          f"active={'yes' if state['active'] else 'no'}  sent={len(msgs)}"
          + (f"  BLACKOUT: {block['title']}" if block else ""))
    save_state(state_path, state)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=os.path.join(HERE, "config.ini"))
    p.add_argument("--once", action="store_true")
    p.add_argument("--csv", help="use a CSV instead of the live API (testing)")
    p.add_argument("--now", help="override current time (UTC ISO), testing only")
    p.add_argument("--test-sms", action="store_true", help="send one test text and exit")
    args = p.parse_args()
    cfg = load_cfg(args.config)
    if args.test_sms:
        ok = send_sms(cfg, "XAUUSD signal bot connected. You'll get signals and news "
                           "alerts here. Not financial advice.")
        print("Test text sent." if ok else "Test text FAILED - check Twilio details.")
        raise SystemExit(0 if ok else 1)
    state_path = os.path.join(HERE, cfg["general"].get("state_file", "state.json"))
    interval = int(cfg["general"].get("check_interval_min", 15))

    while True:
        now = pd.Timestamp(args.now).to_pydatetime() if args.now else datetime.now(timezone.utc)
        try:
            df = data.load_csv(args.csv) if args.csv else data.fetch_twelvedata(
                cfg["data"]["twelvedata_api_key"], cfg["data"]["symbol"])
            if args.csv:
                df = df[df.index + pd.Timedelta("15min") <= now]
            run_once(cfg, df, now, state_path)
        except Exception as e:
            print("Error:", e)
        if args.once:
            break
        # sleep until 20s after the next 15-min bar closes
        nxt = (datetime.now(timezone.utc).replace(second=0, microsecond=0)
               + timedelta(minutes=interval - datetime.now(timezone.utc).minute % interval))
        time.sleep(max(30, (nxt - datetime.now(timezone.utc)).total_seconds() + 20))


if __name__ == "__main__":
    main()
