"""Playwright browser wrapper for headless automation."""

from __future__ import annotations

import base64
import logging
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from browseagent.config import Settings
from browseagent.llm.schemas import ActionSchema, ActionType

logger = logging.getLogger(__name__)


class BrowserDriver:
    """Async Playwright wrapper for browser control."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        return self._page

    async def launch(self) -> None:
        """Launch the browser and create a new page."""
        self._playwright = await async_playwright().start()

        browser_type = getattr(self._playwright, self.settings.browser, self._playwright.chromium)

        self._browser = await browser_type.launch(headless=self.settings.headless)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        logger.info("Browser launched (%s, headless=%s)", self.settings.browser, self.settings.headless)

    async def close(self) -> None:
        """Close the browser and clean up."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for the page to load."""
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        logger.info("Navigated to %s", url)

    async def screenshot(self, full_page: bool = False) -> str:
        """Take a screenshot and return it as a base64-encoded PNG string."""
        raw = await self.page.screenshot(full_page=full_page)
        return base64.b64encode(raw).decode("utf-8")

    async def get_dom_simplified(self) -> str:
        """Extract a simplified DOM representation: visible text, inputs, buttons, links."""
        return await self.page.evaluate("""() => {
            const results = [];
            const MAX_TEXT_LEN = 100;

            function truncate(text) {
                text = text.trim();
                return text.length > MAX_TEXT_LEN ? text.slice(0, MAX_TEXT_LEN) + '...' : text;
            }

            // Links
            document.querySelectorAll('a[href]').forEach(el => {
                const text = truncate(el.innerText);
                if (text) {
                    const selector = el.id ? `#${el.id}` : `a[href="${el.getAttribute('href')}"]`;
                    results.push(`[link] "${text}" → ${selector}`);
                }
            });

            // Buttons
            document.querySelectorAll('button, input[type="submit"], input[type="button"]').forEach(el => {
                const text = truncate(el.innerText || el.value || el.getAttribute('aria-label') || '');
                if (text) {
                    const selector = el.id ? `#${el.id}` :
                        el.name ? `button[name="${el.name}"]` :
                        el.className ? `button.${el.className.split(' ')[0]}` : 'button';
                    results.push(`[button] "${text}" → ${selector}`);
                }
            });

            // Inputs
            document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select').forEach(el => {
                const name = el.name || el.id || el.getAttribute('aria-label') || el.placeholder || '';
                const type = el.type || el.tagName.toLowerCase();
                const selector = el.id ? `#${el.id}` :
                    el.name ? `${el.tagName.toLowerCase()}[name="${el.name}"]` :
                    el.placeholder ? `${el.tagName.toLowerCase()}[placeholder="${el.placeholder}"]` : el.tagName.toLowerCase();
                const value = el.value ? ` (current: "${truncate(el.value)}")` : '';
                results.push(`[input:${type}] "${name}"${value} → ${selector}`);
            });

            // Headings
            document.querySelectorAll('h1, h2, h3').forEach(el => {
                const text = truncate(el.innerText);
                if (text) results.push(`[${el.tagName.toLowerCase()}] "${text}"`);
            });

            // Visible text blocks (paragraphs, list items)
            document.querySelectorAll('p, li, td, span.text, div.content').forEach(el => {
                const text = truncate(el.innerText);
                if (text && text.length > 10) {
                    results.push(`[text] "${text}"`);
                }
            });

            return results.slice(0, 200).join('\\n');
        }""")

    async def get_url(self) -> str:
        """Return the current page URL."""
        return self.page.url

    async def get_title(self) -> str:
        """Return the current page title."""
        return await self.page.title()

    async def execute_action(self, action: ActionSchema) -> bool:
        """Execute a browser action based on the ActionSchema.

        Returns True on success, False on failure.
        """
        try:
            match action.action:
                case ActionType.NAVIGATE:
                    if action.target:
                        await self.navigate(action.target)

                case ActionType.CLICK:
                    if action.target:
                        await self.page.click(action.target, timeout=10000)

                case ActionType.TYPE:
                    if action.target and action.value is not None:
                        await self.page.fill(action.target, action.value, timeout=10000)

                case ActionType.SCROLL:
                    pixels = int(action.value) if action.value else 500
                    direction = -1 if action.target == "up" else 1
                    await self.page.evaluate(f"window.scrollBy(0, {direction * pixels})")

                case ActionType.SELECT:
                    if action.target and action.value is not None:
                        await self.page.select_option(action.target, action.value, timeout=10000)

                case ActionType.PRESS:
                    key = action.target or action.value or "Enter"
                    await self.page.keyboard.press(key)

                case ActionType.EXTRACT:
                    # Extraction is handled by the extractor module; this is a no-op in the driver
                    pass

                case ActionType.WAIT:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)

                case ActionType.DONE:
                    # No browser action needed
                    pass

            return True

        except Exception as exc:
            logger.error("Action failed: %s → %s (error: %s)", action.action.value, action.target, exc)
            return False

    async def load_cookies(self, cookies_path: str) -> None:
        """Load cookies from a JSON file for authenticated sessions."""
        import json
        from pathlib import Path

        path = Path(cookies_path)
        if path.exists():
            with open(path) as f:
                cookies = json.load(f)
            if self._context:
                await self._context.add_cookies(cookies)
                logger.info("Loaded %d cookies from %s", len(cookies), cookies_path)

    async def save_cookies(self, cookies_path: str) -> None:
        """Save current cookies to a JSON file."""
        import json
        from pathlib import Path

        if self._context:
            cookies = await self._context.cookies()
            path = Path(cookies_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(cookies, f, indent=2)
            logger.info("Saved %d cookies to %s", len(cookies), cookies_path)
