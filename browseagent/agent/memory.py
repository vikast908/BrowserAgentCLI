"""Short-term context window management for the agent execution loop."""

from __future__ import annotations

from typing import Any

from browseagent.llm.schemas import ActionSchema, StepRecord


class AgentMemory:
    """Manages the rolling action history and extracted results buffer.

    Keeps a sliding window of recent actions to stay within the LLM's
    context window, and accumulates extracted data across steps.
    """

    def __init__(self, max_history: int = 10) -> None:
        self.max_history = max_history
        self._history: list[dict[str, Any]] = []
        self._results: list[dict[str, Any]] = []
        self._steps: list[StepRecord] = []

    @property
    def action_history(self) -> list[dict[str, Any]]:
        """Return the most recent actions (trimmed to max_history)."""
        return self._history[-self.max_history :]

    @property
    def all_results(self) -> list[dict[str, Any]]:
        """Return all extracted data accumulated so far."""
        return list(self._results)

    @property
    def all_steps(self) -> list[StepRecord]:
        """Return all step records."""
        return list(self._steps)

    @property
    def step_count(self) -> int:
        """Return the total number of steps taken."""
        return len(self._steps)

    def record_action(self, action: ActionSchema, success: bool, error: str | None = None) -> None:
        """Add an action to the history buffer."""
        entry: dict[str, Any] = {
            "action": action.action.value,
            "target": action.target,
            "value": action.value,
            "reasoning": action.reasoning,
        }
        if not success:
            entry["error"] = error or "action failed"

        self._history.append(entry)

    def record_step(self, step: StepRecord) -> None:
        """Record a full step (observation + action + result)."""
        self._steps.append(step)

    def add_results(self, data: list[dict[str, Any]]) -> None:
        """Append extracted data to the results buffer."""
        self._results.extend(data)

    def clear(self) -> None:
        """Reset all memory."""
        self._history.clear()
        self._results.clear()
        self._steps.clear()
