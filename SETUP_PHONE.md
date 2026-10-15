# Run the bot from your phone (no computer)

The bot watches XAUUSD, GBPUSD and EURUSD on the 5-minute, 1-hour and daily
charts. It runs free on GitHub's servers, started every 5 minutes by
cron-job.org (step 6), and sends
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
2. Tap **XAUUSD signals** -> **Run workflow** -> under **What to do** choose
   **Setup check** -> **Run workflow**. When it finishes, tap the run: the
   result is shown at the top in plain words, with ✅/❌ and what to fix.
   If all is well your bot messages you on Telegram.
3. Run it again choosing **Check for signals**. Open the run -> **check** ->
   **Run bot** to see the gold price it read. "sent=0" just means no
   signal right now, which is normal.

## 6. Make it run every 5 minutes (needed for 5-min signals)
GitHub's own timer only runs the bot about once an hour. cron-job.org (free)
starts it every 5 minutes instead.

**a) Make a GitHub access key (token)**
1. Tap your profile picture (top right) -> **Settings** -> scroll to the
   bottom -> **Developer settings** -> **Personal access tokens** ->
   **Fine-grained tokens** -> **Generate new token**.
2. Token name: `cron`. Expiration: the longest offered (e.g. 1 year).
3. Repository access: **Only select repositories** -> pick `gold-bot`.
4. Permissions -> **Repository permissions** -> **Actions** -> set to
   **Read and write**.
5. Tap **Generate token** and copy it (starts `github_pat_`). It's shown
   only once. Keep it private.

**b) Set up cron-job.org**
1. Sign up free at **cron-job.org** and tap **Create cronjob**.
2. **Title:** `gold bot`.
3. **URL** (change YOUR_USERNAME to your GitHub username):
   `https://api.github.com/repos/YOUR_USERNAME/gold-bot/actions/workflows/signals.yml/dispatches`
4. **Execution schedule:** **Every 5 minutes**.
5. Open the **Advanced** tab:
   - **Request method:** `POST`
   - **Headers** -> add these three:
     - `Authorization` = `Bearer ` followed by your token (with a space
       after Bearer)
     - `Accept` = `application/vnd.github+json`
     - `X-GitHub-Api-Version` = `2022-11-28`
   - **Request body:** `{"ref":"main"}`
6. Tap **Create** (or **Save**). Use **Test run**: a result of **204**
   means it worked, and a new run appears in GitHub's Actions tab.
   401 = token wrong; 404 = username/repo name or file path wrong;
   403/422 = token is missing the Actions read-and-write permission.

That's it. The bot now checks every 5 minutes, and sends a short
"bot running" message each weekday morning from 07:00.

**Good to know about the 5-minute chart**
- 5-min signals only run 07:00-21:00 UK time on weekdays (change
  `m5_hours` in config.ini). This keeps within the free data plan
  (about 580 of the 800 daily requests are used).
- 5-min signals come often (several a day across the three pairs). Spreads
  matter a lot on small stops; the bot keeps stops at least 4x the spread.
- The token expires on the date you chose. When it does, make a new one and
  paste it into the cron-job.org Authorization header.

## Good to know
- **Timing:** if a run is late, the bot catches up on bars it missed
  (5-min signals older than 20 minutes are dropped as stale). A late signal says when it
  formed and the price now, so check the price before entering.
- **Pairs/timeframes:** edit `symbols` and `timeframes` in `config.ini`.
- **Several trades at once:** each pair and timeframe signals separately,
  so you can get several open signals together. Their risks add up.
- **Change settings:** edit `config.ini` in the repo (pencil icon), e.g.
  `risk_percent`, `max_risk_percent`, `skip_over_max`.
- **Pause it:** Actions -> XAUUSD signals -> **...** -> **Disable workflow**.
- **Tip:** in Telegram, open your bot's chat -> name at top -> turn
  notifications on, so signals make a sound.
- GitHub pauses schedules on repos with no activity for 60 days. The bot
  saves its memory (state.json) whenever it sends an alert, which keeps it
  active, and GitHub emails you before pausing anything.
