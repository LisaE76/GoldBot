"""SMS (or WhatsApp) delivery through Twilio's REST API."""
import requests


def send_sms(cfg, body):
    s = cfg["sms"]
    numbers = [n.strip() for n in s.get("to_numbers", "").split(",") if n.strip()]
    if s.getboolean("dry_run", fallback=True):
        print("\n----- [DRY RUN] would send to", ", ".join(numbers), "-----")
        print(body)
        print("-" * 50)
        return True
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s['account_sid']}/Messages.json"
    ok = True
    for to in numbers:
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
