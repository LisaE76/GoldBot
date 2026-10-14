"""
Telegram setup check. Explains in plain words what's working and what to fix.
Run from GitHub: Actions -> XAUUSD signals -> Run workflow -> "Setup check".
The result appears at the top of the run page (job summary) and in the log.
"""
import os
import re

import requests

from notifier import clean_token, clean_chat_ids

API = "https://api.telegram.org/bot{}/{}"


class Report:
    def __init__(self):
        self.lines = []

    def ok(self, msg):
        self.lines.append(f"✅ {msg}")

    def bad(self, msg):
        self.lines.append(f"❌ {msg}")

    def info(self, msg):
        self.lines.append(f"ℹ️ {msg}")

    def todo(self, msg):
        self.lines.append(f"👉 **{msg}**")

    def done(self):
        text = "\n\n".join(self.lines)
        print("\n" + "=" * 60 + "\nSETUP CHECK\n" + "=" * 60)
        print(re.sub(r"\*\*", "", text))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("## Telegram setup check\n\n" + text + "\n")


def _call(token, method, **params):
    try:
        r = requests.get(API.format(token, method), params=params, timeout=20)
        return r.json()
    except Exception as e:
        return {"ok": False, "error_code": 0, "description": f"could not reach Telegram ({e})"}


def run(cfg):
    rep = Report()
    s = cfg["sms"]
    raw_token = s.get("telegram_bot_token", "")
    raw_chat = s.get("telegram_chat_id", "")

    # ---- 1. Is the token secret reaching the bot? ----
    if not raw_token or raw_token.startswith("YOUR_"):
        rep.bad("The bot can't see your TELEGRAM_BOT_TOKEN secret.")
        rep.todo("In Settings -> Secrets and variables -> Actions (Secrets tab), check there "
                 "is a secret named exactly TELEGRAM_BOT_TOKEN. Also check "
                 ".github/workflows/signals.yml is the latest version.")
        return rep.done()

    token = clean_token(raw_token)
    if token != raw_token.strip():
        rep.info("Your token had extra characters around it (spaces, quotes or text). "
                 "I've ignored them, but it's worth re-saving the secret cleanly.")
    if not re.fullmatch(r"\d{6,}:[A-Za-z0-9_-]{30,}", token):
        rep.bad(f"The token doesn't look like a Telegram token. It has {len(token)} "
                f"characters; a real one is about 46 and looks like 123456789:AAH...")
        if ":" not in token:
            rep.info("It has no colon (:) in it, so part of it is probably missing.")
        rep.todo("In Telegram open @BotFather -> /mybots -> your bot -> API Token. Tap the "
                 "token once to copy it, then paste it into the TELEGRAM_BOT_TOKEN secret.")
        return rep.done()

    # ---- 2. Does Telegram accept the token? ----
    me = _call(token, "getMe")
    if not me.get("ok"):
        code = me.get("error_code")
        if code == 401:
            rep.bad("Telegram rejected the token (it's old or was revoked).")
        elif code == 404:
            rep.bad("Telegram doesn't recognise the token (part of it is wrong or missing).")
        else:
            rep.bad(f"Couldn't check the token: {me.get('description')}")
        rep.todo("Get the token again from @BotFather -> /mybots -> your bot -> API Token, "
                 "and paste it into the TELEGRAM_BOT_TOKEN secret.")
        return rep.done()
    bot_name = me["result"].get("username", "?")
    rep.ok(f"Your bot token works. Your bot is **@{bot_name}**.")

    # ---- 3. Who has messaged the bot? (gives the correct chat ID) ----
    upd = _call(token, "getUpdates", limit=100)
    if not upd.get("ok") and "webhook" in str(upd.get("description", "")).lower():
        _call(token, "deleteWebhook")
        upd = _call(token, "getUpdates", limit=100)
    chats = {}
    for u in upd.get("result", []) if upd.get("ok") else []:
        msg = u.get("message") or u.get("edited_message") or u.get("my_chat_member") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            name = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) \
                   or chat.get("title") or chat.get("username") or "?"
            chats[str(chat["id"])] = name

    if chats:
        found = ", ".join(f"**{cid}** ({name})" for cid, name in chats.items())
        rep.info(f"People who have messaged @{bot_name}: {found}")
    else:
        rep.info(f"Nobody has messaged @{bot_name} recently, so I can't look up your chat ID.")

    # ---- 4. Is the chat ID right? ----
    ids = clean_chat_ids(raw_chat)
    if not raw_chat or raw_chat.startswith("YOUR_") or not ids:
        rep.bad("The bot can't see a usable TELEGRAM_CHAT_ID secret.")
        if chats:
            rep.todo(f"Set the TELEGRAM_CHAT_ID secret to: {next(iter(chats))}")
        else:
            rep.todo(f"In Telegram, search @{bot_name}, tap Start and send 'hi'. "
                     f"Then run this Setup check again and it will show your chat ID.")
        return rep.done()

    bot_id = token.split(":")[0]
    if bot_id in ids:
        rep.bad("Your TELEGRAM_CHAT_ID is the bot's own ID (the number at the start of the "
                "token), not yours.")

    all_ok = True
    for cid in ids:
        r = _call(token, "sendMessage", chat_id=cid,
                  text="✅ Setup check passed. Your XAUUSD signal bot can message you here.")
        if r.get("ok"):
            rep.ok(f"Sent a test message to chat ID {cid}. Check Telegram!")
        else:
            all_ok = False
            desc = r.get("description", "")
            rep.bad(f"Couldn't message chat ID {cid}: {desc}")
            if chats and cid not in chats:
                rep.todo(f"Change the TELEGRAM_CHAT_ID secret to: {next(iter(chats))}")
            elif "blocked" in desc.lower():
                rep.todo(f"You've blocked @{bot_name}. Open it in Telegram and tap Restart/Unblock.")
            else:
                rep.todo(f"In Telegram, search @{bot_name}, tap Start and send 'hi'. "
                         f"Then run this Setup check again.")
    if all_ok:
        rep.ok("Everything is set up. The bot will check gold every 15 minutes on weekdays.")
    rep.done()


if __name__ == "__main__":
    from main import load_cfg, HERE
    run(load_cfg(os.path.join(HERE, "config.ini")))
