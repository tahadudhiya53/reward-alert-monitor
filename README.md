# PlayToEarn Solana Reward Monitor (free GitHub Actions)

This project watches the PlayToEarn rewards page for an available **Solana Reward** and sends a Telegram alert. It does **not** redeem anything automatically.

## What it does

- Runs in GitHub Actions, so your PC can be completely OFF.
- Uses a saved Playwright browser session so you don't put your PlayToEarn password in the repository.
- Checks the rewards page about every 20 seconds while the runner is active.
- The workflow keeps itself running in fresh GitHub-hosted jobs, staying under GitHub's 6-hour job limit.
- Sends a Telegram alert when the **free $2 Solana Reward**, a **$5 Solana Reward**, or a **$10 Solana Reward** becomes available.
- Does **not** alert for the $2 membership Solana card, Mystery rewards, Amazon/gift-card rewards, or other non-target cards.
- Includes a direct PlayToEarn link so you can open it and redeem manually.

## Exact reward rule

The monitor watches three Solana amounts:

```text
FREE $2 target:     Solana Reward · $2   0/25 → alert when >0/25
MEMBERSHIP $2:      Solana Reward · $2   4/50 → NEVER alert
$5 target:          Solana Reward · $5   → alert when available
$10 target:         Solana Reward · $10  → alert when available
Mystery/Amazon:     non-Solana reward     → NEVER alert
```

The primary $2 free-pool check is **$2 + inventory total 25**. The $5 and $10 Solana rewards are also monitored. The script rejects cards whose surrounding DOM attributes/image labels identify them as membership, premium, Plus, or crown-related.

This means the detector will not simply alert on every card containing “Solana Reward” or every $2 reward.

## 1. Create a Telegram bot

Open `@BotFather` in Telegram and use `/newbot`. Keep the token private.

Then open your new bot and send it `/start`.

To get your chat ID, you can temporarily use:
`https://api.telegram.org/botYOUR_TOKEN/getUpdates`

Look for `"chat":{"id": ...}` in the JSON. Do not publish the token.

## 2. Create your PlayToEarn browser session locally

Install Python 3.11+ and run:

```powershell
py -m pip install -r requirements.txt
py -m playwright install chromium
py setup_session.py
```

A Chromium window opens. Log into your own PlayToEarn account normally. After you are fully logged in, return to the terminal and press Enter.

The script writes:

```text
playwright/auth.json
```

This file contains browser cookies/session data. Treat it like a password.

Convert it to one line of Base64 for a GitHub Secret:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("playwright\auth.json")) | Set-Clipboard
```

Your clipboard now contains the value for the `P2E_STORAGE_STATE_B64` secret.

## 3. Create a public GitHub repository

For the $0 approach, use a **public** repository because standard GitHub-hosted runners are free for public repositories.

Example name:

`playtoearn-solana-monitor`

Upload all files from this project.

**Do not upload `playwright/auth.json`.** `.gitignore` is included to help prevent this.

## 4. Add GitHub Actions secrets

Repository → Settings → Secrets and variables → Actions → New repository secret.

Create:

### Required

`P2E_STORAGE_STATE_B64`
- Value: the Base64 value copied from `auth.json`

`TELEGRAM_BOT_TOKEN`
- Value: your BotFather token

`TELEGRAM_CHAT_ID`
- Value: your Telegram chat ID

### Optional

`TARGET_AMOUNTS`
- Default: `$2,$5,$10`
- Keep this as `$2,$5,$10` to monitor all three target rewards.

`POLL_SECONDS`
- Default: `20`
- Do not set this extremely low. A 15–30 second interval is a reasonable starting point.

## 5. Push to GitHub and start the monitor

After the files are on the `main` branch:

GitHub → Actions → **PlayToEarn Solana Reward Monitor** → Run workflow.

The workflow will first send a Telegram "monitor started" message.

If the saved PlayToEarn session works, it will begin checking the page.

## 6. Test Telegram first

You can test the notification locally:

```powershell
$env:TELEGRAM_BOT_TOKEN="YOUR_TOKEN"
$env:TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
python monitor.py --test-telegram
```

Do not put the real token into any committed file.

## 7. If the monitor says the session is invalid

Run `setup_session.py` again while logged into PlayToEarn, recreate the Base64 value, and replace the `P2E_STORAGE_STATE_B64` GitHub Secret.

Some social/wallet logins can expire or require a new login. The monitor cannot bypass CAPTCHAs, MFA, wallet signatures, or anti-bot challenges.

## How availability is detected

The detector reads the Solana reward cards and applies these filters:

1. Reward text contains **Solana Reward**.
2. Reward amount contains **$2**.
3. Because `FREE_ONLY=true`, the card's inventory total must be **25** (`current/25`).
4. Cards that look like membership/premium/Plus/crown cards are rejected.
5. The reward is considered available only when the current inventory number is greater than zero and the card is not disabled.

So the membership card shown as `4/50` is intentionally ignored even though it is also approximately $2.

The free target can be changed only if PlayToEarn changes its pool size. For the current layout, keep:

```text
FREE_ONLY=true
FREE_STOCK_TOTAL=25
TARGET_AMOUNT=$2
```

## Free/24-7 behavior

The workflow runs for about 5 hours 40 minutes and then dispatches another run. GitHub-hosted jobs have a maximum execution time, so this avoids trying to keep one job alive indefinitely.

GitHub's `workflow_dispatch` event can be triggered from a workflow using `GITHUB_TOKEN`, so the chain can start the next run.

This is a best-effort free solution, not a guaranteed always-on server.

## Safety

- Never add your seed phrase/private key.
- Never commit cookies/session state.
- Never paste GitHub or Telegram secrets into source code.
- If you expose a Telegram bot token, revoke it with BotFather and create a new one.
- Keep redemption manual.
