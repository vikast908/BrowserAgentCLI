"""Page state capture — builds Observation objects from the current browser page."""

from __future__ import annotations

import logging

from browseagent.browser.driver import BrowserDriver
from browseagent.llm.schemas import ObservationSchema

logger = logging.getLogger(__name__)


async def observe_page(driver: BrowserDriver, take_screenshot: bool = False) -> ObservationSchema:
    """Capture the current page state as an ObservationSchema."""
    # Wait for any in-flight navigation to settle
    try:
        await driver.page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass

    try:
        url = await driver.get_url()
    except Exception:
        url = "unknown"

    try:
        title = await driver.get_title()
    except Exception:
        title = ""

    try:
        dom_text = await driver.get_dom_simplified()
    except Exception:
        dom_text = ""

    screenshot_b64: str | None = None
    if take_screenshot:
        try:
            screenshot_b64 = await driver.screenshot()
        except Exception as exc:
            logger.warning("Screenshot capture failed: %s", exc)

    return ObservationSchema(
        url=url,
        title=title,
        dom_text=dom_text,
        screenshot_b64=screenshot_b64,
    )
