# Run the bot from your phone (no computer)

The bot runs free on GitHub's servers every 15 minutes (Mon-Fri) and texts
you. You set it up once in your phone's web browser.

## 1. Get your keys (if you haven't)
- **Twelve Data** (prices): twelvedata.com -> sign up -> copy your API key.
- **Twilio** (texts): twilio.com -> sign up -> copy Account SID, Auth Token,
  and get a Twilio phone number. On the free trial, verify your own mobile
  under "Verified Caller IDs" first.

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
| `TWILIO_ACCOUNT_SID` | starts with AC... |
| `TWILIO_AUTH_TOKEN` | your Twilio auth token |
| `TWILIO_FROM` | your Twilio number, e.g. +15551234567 |
| `SMS_TO` | your mobile, e.g. +447700900000 |
| `ACCOUNT_BALANCE` | your balance in £, e.g. 52 (update as it changes) |

## 5. Test it
1. Repo -> **Actions** tab. If asked, tap **I understand... enable them**.
2. Tap **XAUUSD signals** -> **Run workflow** -> tick **Send a test text**
   -> **Run workflow**. You should get a text within a minute.
3. Run it again **without** the tick. Open the run -> **check** ->
   **Run bot** to see the gold price it read. "sent=0" just means no
   signal right now, which is normal.

That's it. It now runs every 15 minutes on weekdays.

## Good to know
- **Timing:** GitHub sometimes starts scheduled runs 5-15 minutes late at
  busy times. The bot checks the last two bars so it doesn't miss signals,
  but the price may have moved a little from the entry in the text.
- **Change settings:** edit `config.ini` in the repo (pencil icon), e.g.
  `risk_percent`, `max_risk_percent`, `skip_over_max`.
- **Pause it:** Actions -> XAUUSD signals -> **...** -> **Disable workflow**.
- **Twilio trial** texts start with "Sent from your Twilio trial account"
  and use trial credit; upgrade when it runs low.
- GitHub pauses schedules on repos with no activity for 60 days. The bot
  saves its memory (state.json) whenever it sends an alert, which keeps it
  active, and GitHub emails you before pausing anything.
