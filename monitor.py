import argparse
import asyncio
import base64
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

DEFAULT_URL = "https://playtoearn.com/earn"
DEFAULT_POLL = 20

def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()

P2E_URL = env("P2E_URL", DEFAULT_URL)
TARGET_AMOUNTS = [x.strip().lower() for x in env("TARGET_AMOUNTS", "$2,$5,$10").split(",") if x.strip()]
POLL_SECONDS = max(10, int(env("POLL_SECONDS", str(DEFAULT_POLL))))
FREE_STOCK_TOTAL = int(env("FREE_STOCK_TOTAL", "25"))
BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
CHAT_ID = env("TELEGRAM_CHAT_ID")

def telegram(message: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram is not configured.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        r.raise_for_status()
        print("Telegram notification sent.")
        return True
    except Exception as exc:
        print(f"Telegram error: {exc}")
        return False

def decode_storage_state() -> Path:
    encoded = env("P2E_STORAGE_STATE_B64")
    if not encoded:
        raise RuntimeError("Missing P2E_STORAGE_STATE_B64.")

    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError("P2E_STORAGE_STATE_B64 is not valid Base64.") from exc

    if len(raw) > 1_000_000:
        raise RuntimeError("Browser session state is unexpectedly large.")

    tmp = Path(tempfile.mkdtemp(prefix="p2e-auth-")) / "auth.json"
    tmp.write_bytes(raw)
    return tmp

async def extract_rewards(page) -> list[dict[str, Any]]:
    # The visible reward cards currently show values such as 4/50 or 0/25.
    # We collect compact DOM containers containing "Solana Reward" and a current/total pair.
    rows = await page.evaluate(
        """
        () => {
          const out = [];
          const seen = new Set();

          for (const el of document.querySelectorAll('body *')) {
            const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
            if (!/Solana\\s+Reward/i.test(text)) continue;
            if (text.length < 20 || text.length > 700) continue;

            const m = text.match(/(\\d+)\\s*\\/\\s*(\\d+)/);
            if (!m) continue;

            const current = Number(m[1]);
            const total = Number(m[2]);
            if (!Number.isFinite(current) || !Number.isFinite(total)) continue;

            const key = text;
            if (seen.has(key)) continue;
            seen.add(key);

            let disabled = false;
            let membershipLike = false;
            let n = el;
            for (let i = 0; i < 8 && n; i++, n = n.parentElement) {
              if (n.matches?.('[disabled], [aria-disabled="true"]')) disabled = true;
              if (n.querySelector?.('[disabled], [aria-disabled="true"]')) disabled = true;

              const attrs = [
                n.getAttribute?.('aria-label') || '',
                n.getAttribute?.('title') || '',
                n.getAttribute?.('data-testid') || '',
                n.getAttribute?.('data-test') || '',
                n.className?.toString?.() || ''
              ].join(' ');
              if (/membership|premium|plus/i.test(attrs)) membershipLike = true;

              for (const img of n.querySelectorAll?.('img') || []) {
                const imgAttrs = [
                  img.getAttribute?.('alt') || '',
                  img.getAttribute?.('title') || '',
                  img.getAttribute?.('aria-label') || ''
                ].join(' ');
                if (/membership|premium|plus|crown/i.test(imgAttrs)) membershipLike = true;
              }
            }

            out.push({
              text,
              current,
              total,
              membershipLike,
              available: current > 0 && !disabled,
              disabled
            });
          }

          // Prefer the shortest matching container for each visible card.
          out.sort((a, b) => a.text.length - b.text.length);

          const dedup = [];
          for (const row of out) {
            const already = dedup.some(x =>
              x.current === row.current &&
              x.total === row.total &&
              (x.text.includes(row.text) || row.text.includes(x.text))
            );
            if (!already) dedup.push(row);
          }
          return dedup;
        }
        """
    )
    return rows

def choose_target(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        text = row["text"].lower()

        # Only Solana rewards for the configured amounts.
        if "solana reward" not in text:
            continue

        amount_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
        if not amount_match:
            continue
        amount = f"${amount_match.group(1)}".lower()

        if amount not in TARGET_AMOUNTS:
            continue

        # The $2 target must be the FREE 25-item pool. This keeps the
        # membership $2 card (for example 4/50) ignored.
        if amount == "$2" and row["total"] != FREE_STOCK_TOTAL:
            continue

        # Ignore cards explicitly identified as membership/premium/Plus/crown.
        if row.get("membershipLike"):
            continue

        result.append(row)
    return result

async def check_once(page) -> tuple[bool, list[dict[str, Any]]]:
    try:
        await page.reload(wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeoutError:
        # Continue because the DOM may still contain the reward cards.
        print("Page reload timed out; inspecting current DOM.")

    await page.wait_for_timeout(2500)

    body = (await page.locator("body").inner_text(timeout=15000)).lower()
    if "sign in" in body and "logout" not in body:
        raise RuntimeError(
            "PlayToEarn session appears logged out. Refresh the browser session locally "
            "with setup_session.py and replace the GitHub secret."
        )

    rows = await extract_rewards(page)
    targets = choose_target(rows)

    for row in targets:
        print(
            f"TARGET reward: {row['text']} | "
            f"available={row['available']} current={row['current']}/{row['total']}"
        )

    if not targets:
        print("No matching FREE $2 Solana reward card found this check.")

    available = any(row["available"] for row in targets)
    return available, targets

async def run_monitor():
    auth_path = decode_storage_state()

    message = (
        "🟢 PlayToEarn Solana monitor started\\n"
        f"Target: {TARGET_AMOUNT or 'any Solana Reward'}\\n"
        f"Polling: {POLL_SECONDS}s\\n"
        "Redemption is manual."
    )
    telegram(message)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        context = await browser.new_context(
            storage_state=str(auth_path),
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
        )
        page = await context.new_page()

        try:
            await page.goto(P2E_URL, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeoutError:
            print("Initial navigation timed out; continuing.")

        # Keep this job below GitHub's 6-hour hosted-runner limit.
        end_at = time.monotonic() + (5 * 3600 + 40 * 60)

        previous_available = False
        while time.monotonic() < end_at:
            try:
                available, rows = await check_once(page)

                if available and not previous_available:
                    details = "\n".join(
                        f"• {r['text'][:450]}" for r in rows if r["available"]
                    )
                    telegram(
                        "🚨 SOLANA REWARD AVAILABLE!\\n\\n"
                        f"{details}\\n\\n"
                        "Open PlayToEarn NOW and redeem manually:\\n"
                        f"{P2E_URL}"
                    )

                previous_available = available
            except Exception as exc:
                print(f"Check error: {type(exc).__name__}: {exc}")
                telegram(
                    "⚠️ PlayToEarn monitor error\\n"
                    f"{type(exc).__name__}: {str(exc)[:700]}"
                )

            await asyncio.sleep(POLL_SECONDS)

        await browser.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-telegram", action="store_true")
    args = parser.parse_args()

    if args.test_telegram:
        ok = telegram(
            "✅ PlayToEarn monitor Telegram test succeeded.\\n"
            "The bot can send alerts to this chat."
        )
        raise SystemExit(0 if ok else 1)

    asyncio.run(run_monitor())

if __name__ == "__main__":
    main()
