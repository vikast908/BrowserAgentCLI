"""LLM-based task planning — decomposes a natural language task into a browser plan."""

from __future__ import annotations

import logging

from browseagent.llm.client import LLMClient
from browseagent.llm.prompts import build_planner_messages
from browseagent.llm.schemas import PlanSchema

logger = logging.getLogger(__name__)


async def plan_task(client: LLMClient, task: str) -> PlanSchema:
    """Send the task to the LLM planner and return a structured plan.

    Args:
        client: The configured LLM client.
        task: The user's natural language task description.

    Returns:
        A PlanSchema with goal, step estimate, starting URL, and summary.
    """
    messages = build_planner_messages(task)
    logger.info("Planning task: %s", task)

    plan = await client.chat_structured(
        messages=messages,
        schema=PlanSchema,
        temperature=0.2,
    )

    assert isinstance(plan, PlanSchema)
    logger.info(
        "Plan ready: %s (est. %d steps, start: %s)",
        plan.plan_summary,
        plan.steps_estimate,
        plan.first_url,
    )
    return plan
