"""Core perception-action loop — observe, decide, execute, repeat."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from browseagent.agent.memory import AgentMemory
from browseagent.agent.observer import observe_page
from browseagent.agent.planner import plan_task
from browseagent.browser.driver import BrowserDriver
from browseagent.browser.extractor import extract_by_llm_data
from browseagent.config import Settings
from browseagent.llm.client import LLMClient
from browseagent.llm.prompts import build_executor_messages
from browseagent.llm.schemas import (
    ActionSchema,
    ActionType,
    PlanSchema,
    RunResultSchema,
    StepRecord,
)

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Runs the full agent loop: plan → launch browser → observe → act → repeat."""

    def __init__(
        self,
        settings: Settings,
        provider: str | None = None,
        model: str | None = None,
        headless: bool | None = None,
        max_steps: int | None = None,
        take_screenshots: bool | None = None,
    ) -> None:
        self.settings = settings
        if headless is not None:
            self.settings.headless = headless
        self.max_steps = max_steps or settings.max_steps
        self.take_screenshots = take_screenshots if take_screenshots is not None else settings.screenshot

        self.llm = LLMClient(settings, provider=provider, model=model)
        self.driver = BrowserDriver(settings)
        self.memory = AgentMemory()

        self.run_id = uuid4().hex[:12]
        self.plan: PlanSchema | None = None

        # Callbacks for CLI display
        self.on_step: Any = None  # called with (step_number, max_steps, action_description)
        self.on_plan: Any = None  # called with (plan: PlanSchema)
        self.on_error: Any = None  # called with (step_number, error_msg)

    async def run(self, task: str) -> RunResultSchema:
        """Execute a full agent run for the given task.

        Returns a RunResultSchema with all steps, extracted data, and metadata.
        """
        start_time = time.time()
        started_at = datetime.now()

        try:
            # Phase 1: Plan the task
            self.plan = await plan_task(self.llm, task)
            if self.on_plan:
                self.on_plan(self.plan)

            # Phase 2: Launch browser
            await self.driver.launch()
            await self.driver.navigate(self.plan.first_url)

            # Phase 3: Perception-action loop
            status = await self._execution_loop(task)

        except Exception as exc:
            logger.error("Agent run failed: %s", exc)
            status = "failed"
        finally:
            await self.driver.close()

        elapsed = time.time() - start_time

        # Build result
        result = RunResultSchema(
            run_id=self.run_id,
            task=task,
            plan=self.plan or PlanSchema(goal=task, steps_estimate=0, first_url="", plan_summary=""),
            steps=self.memory.all_steps,
            data=self.memory.all_results,
            total_steps=self.memory.step_count,
            elapsed_seconds=round(elapsed, 2),
            status=status,
            started_at=started_at,
            finished_at=datetime.now(),
        )

        return result

    async def _execution_loop(self, task: str) -> str:
        """Run the observe → decide → execute loop.

        Returns the final status string.
        """
        assert self.plan is not None

        for step_num in range(1, self.max_steps + 1):
            # 4a. Observe
            observation = await observe_page(self.driver, take_screenshot=self.take_screenshots)

            # 4b. Ask LLM for next action
            # Truncate DOM to avoid overwhelming the model
            dom_text = observation.dom_text
            if len(dom_text) > 6000:
                dom_text = dom_text[:6000] + "\n... (truncated)"

            messages = build_executor_messages(
                task=task,
                plan_summary=self.plan.plan_summary,
                observation_dom=dom_text,
                action_history=self.memory.action_history,
                screenshot_b64=observation.screenshot_b64,
            )

            action = await self.llm.chat_structured(
                messages=messages,
                schema=ActionSchema,
                temperature=0.1,
                max_tokens=4000,
            )
            assert isinstance(action, ActionSchema)

            # Notify CLI
            action_desc = f"{action.action.value}"
            if action.target:
                action_desc += f" → {action.target}"
            if self.on_step:
                self.on_step(step_num, self.max_steps, action_desc)

            # 4c. Check if done
            if action.action == ActionType.DONE:
                if action.data:
                    normalized = await extract_by_llm_data(action.data)
                    self.memory.add_results(normalized)

                step_record = StepRecord(
                    step_number=step_num,
                    observation=observation,
                    action=action,
                    success=True,
                )
                self.memory.record_step(step_record)
                self.memory.record_action(action, success=True)
                return "completed"

            # 4c. Execute the action
            success = await self.driver.execute_action(action)

            # 4d. Handle extraction results
            if action.action == ActionType.EXTRACT:
                if action.data:
                    # LLM provided data directly
                    normalized = await extract_by_llm_data(action.data)
                    self.memory.add_results(normalized)
                elif action.target:
                    # Try extracting from DOM using the selector
                    from browseagent.browser.extractor import extract_list_items
                    try:
                        # Clean up selector — LLM sometimes wraps in brackets like [h3]
                        selector = action.target.strip()
                        if selector.startswith("[") and selector.endswith("]") and "=" not in selector:
                            selector = selector[1:-1]
                        items = await extract_list_items(self.driver.page, selector)
                        if items:
                            self.memory.add_results(items)
                    except Exception as exc:
                        logger.warning("DOM extraction failed for %s: %s", action.target, exc)

            # 4d. Update memory
            error_msg = None if success else f"Failed to execute {action.action.value} on {action.target}"
            self.memory.record_action(action, success=success, error=error_msg)

            step_record = StepRecord(
                step_number=step_num,
                observation=observation,
                action=action,
                success=success,
                error=error_msg,
            )
            self.memory.record_step(step_record)

            # 4e. Error handling — retry logic
            if not success:
                if self.on_error:
                    self.on_error(step_num, error_msg or "unknown error")

                # Count consecutive failures on same target
                recent_failures = sum(
                    1 for h in self.memory.action_history[-3:]
                    if h.get("error") and h.get("target") == action.target
                )
                if recent_failures >= 2:
                    logger.warning("Skipping after 2 failures on target: %s", action.target)
                    continue

        return "max_steps_reached"
