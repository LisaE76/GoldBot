# Run the bot from your phone (no computer)

The bot runs free on GitHub's servers every 15 minutes (Mon-Fri) and sends
alerts to you on Telegram (free). You set it up once in your phone's browser.

## 1. Get your keys (if you haven't)
- **Twelve Data** (prices): twelvedata.com -> sign up -> copy your API key.
- **Telegram bot** (alerts):
  1. Install Telegram and open a chat with **@BotFather** (blue tick).
  2. Send `/newbot`, give it any name, then a username ending in `bot`
     (e.g. `lisa_gold_signals_bot`).
  3. BotFather replies with a **token** like `123456789:AAH...`. Copy it.
  4. Tap the link BotFather gives to open your new bot and tap **Start**.
     (The bot can't message you until you do this.)
  5. Open a chat with **@userinfobot** and tap **Start**. It replies with
     your **Id**, a number like `512345678`. Copy it; that's your chat ID.

## 2. Make a GitHub account and repository
1. Go to github.com and sign up (free).
2. Tap **+** (top right) -> **New repository**.
3. Name it `gold-bot`, choose **Public**, tap **Create repository**.
   Public is free with unlimited run time. Your keys stay hidden (step 4);
   only the code is visible.

## 3. Upload the files
1. On your phone, open xauusd_signals.zip in your Files app to unzip it.
2. In your repo tap **uploading an existing file** (or **Add file ->
   Upload files**). If you can't see it, use your browser menu ->
   **Request desktop site**.
3. Select all the files from the unzipped folder and tap **Commit changes**.
4. Move the schedule file into place: tap `signals.yml` -> the pencil
   (edit) icon -> in the file-name box at the top, put the cursor before
   `signals.yml` and type `.github/workflows/` so it reads
   `.github/workflows/signals.yml` -> **Commit changes**.

## 4. Add your keys as Secrets
Repo -> **Settings** -> **Secrets and variables** -> **Actions** ->
**New repository secret**. Add each of these (name exactly as shown):

| Name | Value |
|---|---|
| `TWELVEDATA_API_KEY` | your Twelve Data key |
| `TELEGRAM_BOT_TOKEN` | the token from @BotFather |
| `TELEGRAM_CHAT_ID` | your Id from @userinfobot |
| `ACCOUNT_BALANCE` | your balance in £, e.g. 52 (update as it changes) |

## 5. Test it
1. Repo -> **Actions** tab. If asked, tap **I understand... enable them**.
2. Tap **XAUUSD signals** -> **Run workflow** -> tick **Send a test message**
   -> **Run workflow**. Your bot should message you on Telegram within a minute.
3. Run it again **without** the tick. Open the run -> **check** ->
   **Run bot** to see the gold price it read. "sent=0" just means no
   signal right now, which is normal.

That's it. It now runs every 15 minutes on weekdays.

## Good to know
- **Timing:** GitHub sometimes starts scheduled runs 5-15 minutes late at
  busy times. The bot checks the last two bars so it doesn't miss signals,
  but the price may have moved a little from the entry in the alert.
- **Change settings:** edit `config.ini` in the repo (pencil icon), e.g.
  `risk_percent`, `max_risk_percent`, `skip_over_max`.
- **Pause it:** Actions -> XAUUSD signals -> **...** -> **Disable workflow**.
- **Tip:** in Telegram, open your bot's chat -> name at top -> turn
  notifications on, so signals make a sound.
- GitHub pauses schedules on repos with no activity for 60 days. The bot
  saves its memory (state.json) whenever it sends an alert, which keeps it
  active, and GitHub emails you before pausing anything.
