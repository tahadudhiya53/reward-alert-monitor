# Quick start

## A. Telegram
1. Open @BotFather.
2. `/newbot`
3. Create your bot.
4. Copy the bot token somewhere private.
5. Open your new bot and send `/start`.
6. Get your chat ID with:
   `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
   Find `chat.id`.

## B. PlayToEarn session
1. On Windows, make sure `py --version` works.
2. Double-click `setup_session.bat`.
3. Log into PlayToEarn in the Chromium window.
4. When the rewards page is visible, press Enter in the terminal.
5. Create the Base64 value:
   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("playwright\auth.json")) | Set-Clipboard
   ```

## C. GitHub
Create a PUBLIC repository and upload the project files.

Add repository secrets:
- `P2E_STORAGE_STATE_B64`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TARGET_AMOUNTS` = `$2,$5,$10`
- `POLL_SECONDS` = `20`

Then:
Actions → PlayToEarn Solana Reward Monitor → Run workflow.

## D. Test
The first message should say:
`🟢 PlayToEarn Solana monitor started`

If the session is valid, the workflow starts checking.

When a target reward is available:
`🚨 SOLANA REWARD AVAILABLE!`

Open the PlayToEarn link immediately and redeem manually.

## If you get "logged out"
Repeat the local session setup and replace `P2E_STORAGE_STATE_B64`.

## If you get "no Solana reward found"
PlayToEarn may have changed its DOM. Send the workflow log (remove secrets) and a fresh screenshot of the Redeem popup so the selector can be updated.
