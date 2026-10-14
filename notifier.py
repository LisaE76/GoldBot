"""Alert delivery: Telegram (free) or SMS/WhatsApp through Twilio."""
import requests


def _split(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def send_sms(cfg, body):
    """Send an alert using the configured provider. Returns True on success."""
    s = cfg["sms"]
    provider = s.get("provider", "telegram").strip().lower()
    if s.getboolean("dry_run", fallback=True):
        who = s.get("telegram_chat_id") if provider == "telegram" else s.get("to_numbers")
        print(f"\n----- [DRY RUN] would send via {provider} to {who} -----")
        print(body)
        print("-" * 50)
        return True
    if provider == "telegram":
        return _send_telegram(s, body)
    return _send_twilio(s, body)


def _send_telegram(s, body):
    token = s.get("telegram_bot_token", "").strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = True
    for chat_id in _split(s.get("telegram_chat_id")):
        try:
            r = requests.post(url, data={"chat_id": chat_id, "text": body}, timeout=20)
            j = r.json()
            if not j.get("ok"):
                print(f"Telegram to {chat_id} failed: {j.get('description', r.text[:200])}")
                if "chat not found" in str(j.get("description", "")).lower():
                    print("Tip: open your bot in Telegram and tap Start first, "
                          "and check the chat ID.")
                ok = False
        except Exception as e:
            print(f"Telegram to {chat_id} failed: {e}")
            ok = False
    return ok


def _send_twilio(s, body):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s['account_sid']}/Messages.json"
    ok = True
    for to in _split(s.get("to_numbers")):
        sender = s["from_number"]
        if to.startswith("whatsapp:") and not sender.startswith("whatsapp:"):
            sender = "whatsapp:" + sender
        try:
            r = requests.post(url, data={"From": sender, "To": to, "Body": body},
                              auth=(s["account_sid"], s["auth_token"]), timeout=20)
            if r.status_code >= 300:
                print(f"SMS to {to} failed: {r.status_code} {r.text[:200]}")
                ok = False
        except Exception as e:
            print(f"SMS to {to} failed: {e}")
            ok = False
    return ok
