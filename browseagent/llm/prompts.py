"""System prompts for the planner and executor LLM calls."""

PLANNER_SYSTEM_PROMPT = """\
You are a browser automation planner. Given a task, return ONLY valid JSON:
{"goal":"...","steps_estimate":<int>,"first_url":"...","plan_summary":"..."}

Pick the most direct starting URL. Be realistic about step counts (5-15).
"""


EXECUTOR_SYSTEM_PROMPT = """\
You control a web browser. Given the current page state, decide the next action.
Return ONLY valid JSON:
{"action":"<type>","target":"<selector or url>","value":"<text or null>","reasoning":"...","confidence":0.9,"data":null}

Actions: navigate (target=url), click (target=css), type (target=css, value=text), press (target=key like Enter/Tab), scroll (target=up/down), extract (target=css), wait, done (data=[{...}]).

Rules:
- After typing in a search box, use press with target Enter.
- For done, include extracted data in the data field as [{...},...].
- Use specific CSS selectors (IDs, names, aria-labels).
"""


def build_planner_messages(task: str) -> list[dict]:
    """Build the message list for the planner LLM call."""
    return [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Task: {task}"},
    ]


def build_executor_messages(
    task: str,
    plan_summary: str,
    observation_dom: str,
    action_history: list[dict],
    screenshot_b64: str | None = None,
) -> list[dict]:
    """Build the message list for the executor LLM call."""
    # Compact history
    history_text = ""
    if action_history:
        lines = []
        for i, entry in enumerate(action_history[-5:], 1):
            line = f"{entry.get('action','?')}:{entry.get('target','')}"
            if entry.get("error"):
                line += f" [FAIL]"
            lines.append(line)
        history_text = ", ".join(lines)

    text = f"Task: {task}\nPlan: {plan_summary}\nURL DOM:\n{observation_dom}\nHistory: {history_text or 'none'}\nNext action?"

    # Skip vision for local models to save tokens
    if screenshot_b64:
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
            {"type": "text", "text": text},
        ]
    else:
        user_content = text

    return [
        {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
