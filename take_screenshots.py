"""Screenshot admin panel pages for diploma thesis."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT_DIR = Path(r"D:\EcoBot-Docs\attachments\admin_screens")
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "http://localhost/admin"

PAGES = [
    ("login",       f"{BASE}/login",                    None),
    ("dashboard",   f"{BASE}/",                         None),
    ("bio_list",    f"{BASE}/biological",               None),
    ("bio_edit",    f"{BASE}/biological/1/edit",        None),
    ("settings",    f"{BASE}/settings",                 None),
    ("testing",     f"{BASE}/testing",                  None),
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # Login first
        await page.goto(f"{BASE}/login", wait_until="networkidle")
        await page.screenshot(path=OUT_DIR / "01_login.png", full_page=True)
        print("01_login.png OK")

        await page.fill('input[name="username"]', "admin")
        await page.fill('input[name="password"]', "admin")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/admin/**", timeout=8000)

        # Dashboard - viewport only
        await page.goto(f"{BASE}/", wait_until="networkidle")
        await page.screenshot(path=OUT_DIR / "02_dashboard.png")
        print("02_dashboard.png OK")

        # Bio list - viewport only (full page too long)
        await page.goto(f"{BASE}/biological", wait_until="networkidle")
        await page.wait_for_timeout(300)
        await page.screenshot(path=OUT_DIR / "03_bio_list.png")
        print("03_bio_list.png OK")

        # Bio edit - click first "Открыть" button
        first_open = await page.query_selector("a.btn-details")
        if first_open:
            href = await first_open.get_attribute("href")
            await page.goto(f"http://localhost{href}", wait_until="networkidle")
            await page.wait_for_timeout(500)
            await page.screenshot(path=OUT_DIR / "04_bio_edit.png", full_page=True)
            print(f"04_bio_edit.png OK  (url: {href})")
        else:
            print("  SKIP 04_bio_edit: no btn-details found")

        # Settings
        await page.goto(f"{BASE}/settings", wait_until="networkidle")
        await page.wait_for_timeout(300)
        await page.screenshot(path=OUT_DIR / "05_settings.png")
        print("05_settings.png OK")

        # Testing
        await page.goto(f"{BASE}/testing", wait_until="networkidle")
        await page.wait_for_timeout(300)
        await page.screenshot(path=OUT_DIR / "06_testing.png")
        print("06_testing.png OK")

        await browser.close()
        print(f"\nDone -> {OUT_DIR}")

asyncio.run(main())
