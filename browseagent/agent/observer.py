"""Page state capture — builds Observation objects from the current browser page."""

from __future__ import annotations

import logging

from browseagent.browser.driver import BrowserDriver
from browseagent.llm.schemas import ObservationSchema

logger = logging.getLogger(__name__)


async def observe_page(driver: BrowserDriver, take_screenshot: bool = False) -> ObservationSchema:
    """Capture the current page state as an ObservationSchema.

    Args:
        driver: The active BrowserDriver instance.
        take_screenshot: Whether to capture a screenshot (adds latency + tokens).

    Returns:
        An ObservationSchema with URL, title, simplified DOM, and optional screenshot.
    """
    url = await driver.get_url()
    title = await driver.get_title()
    dom_text = await driver.get_dom_simplified()

    screenshot_b64: str | None = None
    if take_screenshot:
        try:
            screenshot_b64 = await driver.screenshot()
        except Exception as exc:
            logger.warning("Screenshot capture failed: %s", exc)

    observation = ObservationSchema(
        url=url,
        title=title,
        dom_text=dom_text,
        screenshot_b64=screenshot_b64,
    )

    logger.debug("Observed: %s (%s) — DOM length: %d chars", url, title, len(dom_text))
    return observation
