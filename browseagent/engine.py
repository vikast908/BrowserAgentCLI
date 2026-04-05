"""Unified engine layer — browser-use for interactive tasks, crawl4ai for extraction."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────
class EngineResult:
    """Standardized result from any engine."""

    def __init__(self) -> None:
        self.run_id: str = uuid4().hex[:12]
        self.task: str = ""
        self.data: list[dict[str, Any]] = []
        self.total_steps: int = 0
        self.elapsed_seconds: float = 0.0
        self.status: str = "completed"
        self.started_at: datetime = datetime.now()
        self.finished_at: datetime | None = None


# ── Callbacks type ────────────────────────────────────
StepCallback = Callable[[int, int, str], None]  # (step, max_steps, description)
ScreenshotCallback = Callable[[str], None]  # (base64_png)
ErrorCallback = Callable[[int, str], None]  # (step, error_msg)
StatusCallback = Callable[[str, dict[str, Any]], None]  # (status, data)


# ── Task classification ──────────────────────────────
def is_extraction_task(task: str) -> bool:
    """Detect if a task is pure data extraction (no interaction needed)."""
    task_lower = task.lower()
    extraction_signals = [
        "scrape", "extract", "get the", "get all", "get titles", "get prices",
        "get names", "get links", "get data", "get information",
        "list of", "table from", "prices from", "titles from",
    ]
    interaction_signals = [
        "fill", "submit", "login", "sign in", "click", "type",
        "search for", "navigate", "form", "register", "sign up",
    ]

    has_extraction = any(s in task_lower for s in extraction_signals)
    has_interaction = any(s in task_lower for s in interaction_signals)

    # Only pure extraction if no interaction is needed
    # Also need a URL to extract from
    has_url = "http" in task_lower or ".com" in task_lower or ".org" in task_lower
    return has_extraction and not has_interaction and has_url


def _extract_url(task: str) -> str | None:
    """Pull a URL from the task string."""
    match = re.search(r'https?://\S+', task)
    if match:
        return match.group(0).rstrip('.,;:')
    # Try domain patterns
    match = re.search(r'(?:www\.)?(\w[\w.-]+\.\w{2,})', task)
    if match:
        return f"https://{match.group(0)}"
    return None


# ── Crawl4AI Engine (fast extraction, no LLM per action) ─
async def run_crawl4ai(
    task: str,
    on_status: StatusCallback | None = None,
    on_screenshot: ScreenshotCallback | None = None,
) -> EngineResult:
    """Fast data extraction using crawl4ai — no LLM-per-action loop."""
    from crawl4ai import AsyncWebCrawler

    result = EngineResult()
    result.task = task
    start = time.time()

    url = _extract_url(task)
    if not url:
        result.status = "failed"
        result.finished_at = datetime.now()
        return result

    if on_status:
        on_status("planning", {"task": task})
        on_status("launching", {})

    try:
        async with AsyncWebCrawler(headless=True) as crawler:
            crawl_result = await crawler.arun(url=url)

            if crawl_result.success and crawl_result.markdown:
                # Parse the markdown content into structured data
                # Extract any tables or lists from the markdown
                lines = crawl_result.markdown.strip().split("\n")
                items = []
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("---"):
                        items.append({"content": line})

                result.data = items[:100]  # Cap at 100 items
                result.status = "completed"
                result.total_steps = 1
            else:
                result.status = "failed"

    except Exception as exc:
        logger.error("Crawl4AI failed: %s", exc)
        result.status = "failed"

    result.elapsed_seconds = round(time.time() - start, 2)
    result.finished_at = datetime.now()
    return result


# ── Browser-Use Engine (interactive, batched actions) ─
async def run_browser_use(
    task: str,
    model: str = "qwen/qwen3.5-9b",
    provider: str = "lm_studio",
    lm_studio_url: str = "http://localhost:1234",
    max_steps: int = 40,
    max_actions_per_step: int = 10,
    headless: bool = False,
    on_step: StepCallback | None = None,
    on_screenshot: ScreenshotCallback | None = None,
    on_error: ErrorCallback | None = None,
    on_status: StatusCallback | None = None,
    pause_event: asyncio.Event | None = None,
    stop_flag: Callable[[], bool] | None = None,
    takeover_flag: Callable[[], bool] | None = None,
    get_page_callback: Callable | None = None,
) -> EngineResult:
    """Run a task using browser-use with batched actions for speed."""
    from browser_use import Agent, BrowserProfile, BrowserSession, ChatOpenAI

    result = EngineResult()
    result.task = task
    start = time.time()
    step_counter = [0]

    if on_status:
        on_status("planning", {"task": task})

    # Build LLM client
    if provider == "lm_studio":
        llm = ChatOpenAI(
            model=model,
            base_url=f"{lm_studio_url}/v1",
            api_key="lm-studio",
            temperature=0.1,
        )
    elif provider == "openai":
        llm = ChatOpenAI(model=model, temperature=0.1)
    elif provider == "anthropic":
        from browser_use import ChatLiteLLM
        llm = ChatLiteLLM(model=f"anthropic/{model}", temperature=0.1)
    else:
        llm = ChatOpenAI(
            model=model,
            base_url=f"{lm_studio_url}/v1",
            api_key="lm-studio",
            temperature=0.1,
        )

    # Browser config — tuned for speed
    browser_profile = BrowserProfile(
        headless=headless,
        highlight_elements=not headless,
        viewport={"width": 1280, "height": 800},
        wait_between_actions=0.1,
        minimum_wait_page_load_time=0.2,
    )

    browser_session = BrowserSession(browser_profile=browser_profile)

    # Step callback for UI updates
    def new_step_callback(browser_state, agent_output, step_number):
        step_counter[0] = step_number
        if agent_output and agent_output.action:
            actions = agent_output.action
            desc_parts = []
            for act in actions:
                act_dict = act.model_dump(exclude_none=True, exclude_unset=True)
                # Get the actual action from the dict
                for key, val in act_dict.items():
                    if val is not None and key != "reasoning":
                        desc_parts.append(f"{key}")
                        break
            desc = ", ".join(desc_parts) if desc_parts else "thinking"
        else:
            desc = "thinking"

        if on_step:
            on_step(step_number, max_steps, desc)

    # Screenshot streaming on each step
    async def on_step_end(agent):
        nonlocal browser_session

        # Stream screenshot to UI
        if on_screenshot:
            try:
                page = await browser_session.get_current_page()
                if page:
                    import base64
                    # Use CDP to capture screenshot
                    session_id = await page._ensure_session()
                    ss_result = await page._client.send(
                        "Page.captureScreenshot",
                        {"format": "png"},
                        session_id=session_id,
                    )
                    if ss_result and "data" in ss_result:
                        on_screenshot(ss_result["data"])
            except Exception as exc:
                logger.debug("Screenshot capture failed: %s", exc)

        # Handle pause
        if pause_event and not pause_event.is_set():
            while not pause_event.is_set():
                if stop_flag and stop_flag():
                    break
                await asyncio.sleep(0.3)

        # Handle takeover
        if takeover_flag and takeover_flag():
            while takeover_flag() and not (stop_flag and stop_flag()):
                await asyncio.sleep(0.5)

    # Expose page for manual control
    async def on_step_start(agent):
        if get_page_callback:
            try:
                page = await browser_session.get_current_page()
                get_page_callback(page)
            except Exception:
                pass

    if on_status:
        on_status("launching", {})

    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser_session,
            max_actions_per_step=max_actions_per_step,
            use_vision=False,  # Text-only for speed with local models
            register_new_step_callback=new_step_callback,
            message_compaction=True,
            max_clickable_elements_length=2000,  # Small DOM for fast local inference
            enable_planning=False,  # Skip separate planning step
            llm_timeout=300,  # 5 min timeout for local models
            step_timeout=300,
            extend_system_message=(
                "\n\nIMPORTANT: Do NOT use the 'extract' tool — it is very slow. "
                "Instead, read the information directly from the page DOM provided to you "
                "and use the 'done' action to return results immediately. "
                "You can see all the text content in the page state — just read it and return the answer."
            ),
        )

        history = await agent.run(
            max_steps=max_steps,
            on_step_start=on_step_start,
            on_step_end=on_step_end,
        )

        # Extract results from history
        if history:
            final = history.final_result()
            if final:
                # Try to parse as JSON
                try:
                    parsed = json.loads(final)
                    if isinstance(parsed, list):
                        result.data = parsed
                    elif isinstance(parsed, dict):
                        result.data = [parsed]
                    else:
                        result.data = [{"result": str(final)}]
                except (json.JSONDecodeError, TypeError):
                    result.data = [{"result": str(final)}]

            result.total_steps = len(history.history) if history.history else step_counter[0]
            result.status = "completed"
        else:
            result.status = "failed"

    except Exception as exc:
        logger.error("Browser-use agent failed: %s", exc)
        result.status = "failed"
        if on_error:
            on_error(step_counter[0], str(exc))
    finally:
        try:
            await browser_session.close()
        except Exception:
            pass

    result.elapsed_seconds = round(time.time() - start, 2)
    result.finished_at = datetime.now()
    return result


# ── Smart Router ──────────────────────────────────────
async def run_task(
    task: str,
    model: str = "qwen/qwen3.5-9b",
    provider: str = "lm_studio",
    lm_studio_url: str = "http://localhost:1234",
    max_steps: int = 40,
    headless: bool = False,
    on_step: StepCallback | None = None,
    on_screenshot: ScreenshotCallback | None = None,
    on_error: ErrorCallback | None = None,
    on_status: StatusCallback | None = None,
    **kwargs,
) -> EngineResult:
    """Smart router — picks the fastest engine for the task."""

    # For pure extraction tasks, try crawl4ai first (10-50x faster)
    if is_extraction_task(task):
        logger.info("Routing to crawl4ai (extraction task detected)")
        if on_status:
            on_status("info", {"message": "Fast extraction mode (crawl4ai)"})
        result = await run_crawl4ai(task, on_status=on_status, on_screenshot=on_screenshot)
        if result.status == "completed" and result.data:
            return result
        # Fall through to browser-use if crawl4ai didn't get useful data
        logger.info("Crawl4AI insufficient, falling back to browser-use")

    # Interactive or complex tasks — use browser-use
    logger.info("Routing to browser-use (interactive task)")
    return await run_browser_use(
        task=task,
        model=model,
        provider=provider,
        lm_studio_url=lm_studio_url,
        max_steps=max_steps,
        headless=headless,
        on_step=on_step,
        on_screenshot=on_screenshot,
        on_error=on_error,
        on_status=on_status,
        **kwargs,
    )
