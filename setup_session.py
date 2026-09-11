import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

URL = "https://playtoearn.com/earn"
AUTH_DIR = Path("playwright")
AUTH_FILE = AUTH_DIR / "auth.json"

async def main():
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("Opening PlayToEarn.")
        print("Log in to YOUR account normally in the browser.")
        print("Do not give your password, seed phrase, or private key to this script or anyone else.")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        input("After you are fully logged in and the rewards page is visible, press Enter here... ")

        # Save cookies/local storage only; no passwords are written by this script.
        await context.storage_state(path=str(AUTH_FILE))
        print(f"\nSaved session to: {AUTH_FILE.resolve()}")
        print("IMPORTANT: treat this file as sensitive and never commit it to GitHub.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
