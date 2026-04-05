"""Typed action primitives for browser automation.

This module provides standalone action functions that map directly to
Playwright calls. The BrowserDriver.execute_action() method is the primary
entry point, but these functions can be used independently for testing.
"""

from __future__ import annotations

from playwright.async_api import Page


async def navigate_to(page: Page, url: str, timeout: int = 30000) -> None:
    """Navigate to a URL and wait for DOM content to load."""
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)


async def click_element(page: Page, selector: str, timeout: int = 10000) -> None:
    """Click an element identified by a CSS selector."""
    await page.click(selector, timeout=timeout)


async def type_text(page: Page, selector: str, text: str, timeout: int = 10000) -> None:
    """Clear an input field and type text into it."""
    await page.fill(selector, text, timeout=timeout)


async def scroll_page(page: Page, direction: str = "down", pixels: int = 500) -> None:
    """Scroll the page up or down by a given number of pixels."""
    sign = -1 if direction == "up" else 1
    await page.evaluate(f"window.scrollBy(0, {sign * pixels})")


async def select_option(page: Page, selector: str, value: str, timeout: int = 10000) -> None:
    """Select a dropdown option by value."""
    await page.select_option(selector, value, timeout=timeout)


async def wait_for_idle(page: Page, timeout: int = 15000) -> None:
    """Wait for the page to reach network idle state."""
    await page.wait_for_load_state("networkidle", timeout=timeout)


async def press_key(page: Page, key: str) -> None:
    """Press a keyboard key (e.g., 'Enter', 'Escape')."""
    await page.keyboard.press(key)


async def hover_element(page: Page, selector: str, timeout: int = 10000) -> None:
    """Hover over an element."""
    await page.hover(selector, timeout=timeout)
