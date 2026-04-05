# BrowseAgent CLI — Functional Plan

## Overview

BrowseAgent is a command-line tool that accepts natural language tasks and executes them by autonomously controlling a headless browser. The user describes what they want (e.g., "get me software engineering leads from LinkedIn in Mumbai") and the agent plans, navigates, extracts, and returns structured data — all without manual browser interaction.

---

## Pilot Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Rich ecosystem for both AI and browser tooling |
| CLI framework | `click` or `typer` | Clean argument parsing, help generation |
| Browser automation | `Playwright` (async) | Headless Chromium; supports screenshots, DOM, network |
| LLM (local) | Qwen3-8B via LM Studio | OpenAI-compatible API at `localhost:1234` |
| LLM (cloud, optional) | Claude / GPT-4o | Fallback or higher-quality planning |
| Output rendering | `rich` | Pretty tables, spinners, progress in terminal |
| Structured output | Pydantic v2 | Validates LLM-generated action plans |
| Data persistence | JSON / CSV / SQLite | Exportable results |

---

## CLI Interface

### Commands

```bash
# Execute a browser task (primary command)
agent run "get software engineer leads from LinkedIn in Mumbai"

# Run with options
agent run "scrape pricing from competitor.com" \
  --model qwen3-8b \           # LLM to use
  --output leads.csv \         # save results to file
  --headless false \           # show browser window for debugging
  --max-steps 30 \             # cap execution steps
  --screenshot                 # save screenshots of each step

# Use cloud model instead of local
agent run "fill out the contact form on example.com" --provider anthropic

# List past runs
agent history

# Replay a past run
agent replay <run-id>

# Configure credentials / settings
agent config set lm-studio-url http://localhost:1234
agent config set default-model qwen3-8b
```

### Example session in terminal
```
$ agent run "find 10 software engineer leads on LinkedIn in Mumbai"

◎ Planning task...
◎ Launching browser (headless)...
◎ Step 1/30 → navigate to linkedin.com/search/results/people
◎ Step 2/30 → type "software engineer Mumbai" in search
◎ Step 3/30 → apply filter: location = Mumbai
◎ Step 4/30 → extract names, titles, companies from results
◎ Step 5/30 → scroll and load more results
...
✓ Task complete in 12 steps (34s)

┌────────────────┬──────────────────────┬──────────────┐
│ Name           │ Title                │ Company      │
├────────────────┼──────────────────────┼──────────────┤
│ Priya Sharma   │ Software Engineer    │ Infosys      │
│ Amit Kulkarni  │ Sr. SWE              │ Flipkart     │
│ ...            │ ...                  │ ...          │
└────────────────┴──────────────────────┴──────────────┘

Saved to: leads_20260405_143211.csv
```

---

## Core Architecture

### Component Breakdown

```
browseagent/
├── cli/
│   ├── main.py          # Click entry points (run, history, config)
│   └── display.py       # Rich terminal UI helpers
├── agent/
│   ├── planner.py       # LLM-based task decomposition
│   ├── executor.py      # Step-by-step action loop
│   ├── observer.py      # Page state capture (DOM + screenshot)
│   └── memory.py        # Short-term context window management
├── browser/
│   ├── driver.py        # Playwright wrapper (launch, navigate, interact)
│   ├── actions.py       # Typed action primitives
│   └── extractor.py     # Data extraction from DOM
├── llm/
│   ├── client.py        # Unified LLM client (local + cloud)
│   ├── prompts.py       # System prompts and few-shot examples
│   └── schemas.py       # Pydantic schemas for structured output
├── storage/
│   ├── runs.py          # Run history storage (SQLite)
│   └── export.py        # CSV / JSON export
└── config.py            # Settings from ~/.browseagent/config.yaml
```

---

## Execution Pipeline (Step by Step)

### Phase 1 — Task Reception

1. User runs `agent run "<task>"` from terminal
2. CLI validates input, loads config (model, LM Studio URL, etc.)
3. A new **Run** object is created with a unique ID, timestamp, and raw task string
4. Rich progress spinner starts

---

### Phase 2 — Task Planning (LLM Call #1)

The task string is sent to the LLM with a **Planner prompt**:

**System prompt (planner):**
```
You are a browser automation expert. Given a task, break it into a list of
high-level browser steps. Return only valid JSON matching the PlanSchema.
Each step has: type (navigate|click|type|scroll|extract|wait|done),
a human-readable description, and optional parameters.
```

**LLM returns structured JSON (PlanSchema):**
```json
{
  "goal": "Find 10 software engineer leads from LinkedIn in Mumbai",
  "steps_estimate": 12,
  "first_url": "https://www.linkedin.com/search/results/people/",
  "plan_summary": "Search LinkedIn, apply location filter, extract profile data"
}
```

This phase ensures the agent has a clear starting URL and rough step count before browser launch.

---

### Phase 3 — Browser Launch

1. Playwright launches Chromium (headless by default, visible with `--headless false`)
2. Browser context is created with:
   - Saved cookies / session state if available (for logged-in sites)
   - A realistic user-agent string
   - Default viewport: 1280×800
3. Navigate to `first_url` from the plan

---

### Phase 4 — Perception → Action Loop

This is the core loop. It runs until the task is complete or `max-steps` is hit.

**Each iteration:**

#### 4a. Observe the current page state
- Capture a **screenshot** (PNG, downscaled to ~800px wide for token efficiency)
- Extract **simplified DOM** — visible text, input fields, buttons, links (not full HTML)
- Record current URL, page title
- Package all this into an **Observation object**

#### 4b. LLM decides next action (LLM Call #2...N)

**System prompt (executor):**
```
You are controlling a web browser to complete a task. You will receive:
- The original task
- A screenshot of the current page (as base64 image)
- The page's simplified DOM (text/inputs/buttons)
- History of past actions taken

Decide the SINGLE best next action. Return valid JSON matching ActionSchema.
Available actions: navigate, click, type, scroll, select, extract, done.
If the task is complete, return action type = "done" with extracted data.
```

**LLM returns ActionSchema:**
```json
{
  "action": "type",
  "target": "#search-input",
  "value": "software engineer Mumbai",
  "reasoning": "Need to enter search query in LinkedIn search bar",
  "confidence": 0.92
}
```

#### 4c. Execute the action
The executor maps the LLM's action JSON to a Playwright call:

| LLM Action | Playwright call |
|---|---|
| `navigate` | `page.goto(url)` |
| `click` | `page.click(selector)` |
| `type` | `page.fill(selector, value)` |
| `scroll` | `page.evaluate("window.scrollBy(0, 500)")` |
| `select` | `page.select_option(selector, value)` |
| `extract` | Custom DOM → structured data extractor |
| `wait` | `page.wait_for_load_state("networkidle")` |
| `done` | Ends loop, returns collected data |

#### 4d. Update memory
- Append action + result to **short-term action history**
- Trim to last N actions to stay within LLM context window
- If data was extracted, append to the **results buffer**

#### 4e. Error handling
If a selector is not found, or the action fails:
- Retry once with a broader selector (LLM re-prompted with error context)
- After 2 failures on same step: skip and continue
- Log failures for post-run review

---

### Phase 5 — Data Extraction

When the LLM determines it has found the needed data, it returns structured JSON:

```json
{
  "action": "done",
  "data": [
    {
      "name": "Priya Sharma",
      "title": "Software Engineer",
      "company": "Infosys",
      "location": "Mumbai",
      "profile_url": "https://linkedin.com/in/priya-sharma-123"
    }
  ]
}
```

The `extractor.py` module can also run a targeted extraction pass — given a selector pattern (e.g., all profile cards on LinkedIn results page) it parses the DOM and returns clean structured records.

---

### Phase 6 — Output & Export

1. Results are displayed in the terminal as a Rich table
2. A run summary is shown: steps taken, time elapsed, items collected
3. Data is saved to:
   - `~/.browseagent/runs/<run-id>/results.json` (always)
   - User-specified file (CSV/JSON) if `--output` flag was used
4. Run metadata is written to SQLite for `agent history` lookups
5. Screenshots (if `--screenshot` flag) saved to run folder

---

## LLM Client — Local vs Cloud

The `llm/client.py` provides a unified interface that works with both LM Studio (local) and cloud APIs.

### LM Studio (local, default)

LM Studio exposes an OpenAI-compatible REST API:
```python
client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
response = client.chat.completions.create(
    model="qwen3-8b",
    messages=[...],
    response_format={"type": "json_object"},
    max_tokens=1000,
)
```

**Model**: Qwen3-8B (4-bit quantised, runs on 8GB VRAM or Apple Silicon)

**Why Qwen3-8B?**
- Strong instruction following for structured JSON output
- Good at reading simplified DOM / HTML fragments
- Fast enough for 1–2s per decision step
- Fits in consumer GPU / Mac M-series

### Cloud fallback (Anthropic / OpenAI)

When `--provider anthropic` is passed, the same interface uses the Anthropic API with Claude Sonnet. Cloud models handle:
- More complex reasoning tasks
- Longer DOM contexts
- Vision-heavy pages (Claude's vision is stronger than Qwen3-8B)

---

## Prompt Design (Key Prompts)

### Vision + DOM hybrid prompt

Because Qwen3-8B has vision support, each executor call sends:
1. A compressed screenshot (base64, ~400px wide)
2. Simplified DOM text (visible text + interactable elements only)
3. Last 5 actions taken
4. Original task goal

This gives the model both visual context and exact element selectors — avoiding hallucinated selectors that vision-only approaches suffer from.

### Few-shot examples in system prompt

The system prompt includes 2–3 worked examples of task → observation → action sequences, which dramatically improves JSON reliability with smaller models like Qwen3-8B.

---

## Configuration File

`~/.browseagent/config.yaml`
```yaml
default_provider: lm_studio
lm_studio_url: http://localhost:1234
default_model: qwen3-8b
headless: true
max_steps: 40
screenshot: false
browser: chromium  # chromium | firefox | webkit
data_dir: ~/.browseagent/runs
```

---

## Limitations & Guardrails (v1)

| Limitation | Mitigation |
|---|---|
| Sites requiring login (LinkedIn, etc.) | User pre-logs in via `agent login linkedin`; cookies saved |
| CAPTCHAs / bot detection | Flag to user; pause and allow manual solve |
| Dynamic JS-heavy SPAs | Playwright waits for `networkidle` before each observation |
| LLM hallucinating selectors | DOM extractor validates selector exists before action |
| Qwen3-8B JSON reliability | `response_format: json_object` + retry with stricter prompt |
| Infinite scroll / pagination | Max-steps cap; smart "load more" detection |

---

## Phased Build Plan (for Claude Code)

### Phase 1 — Skeleton (Week 1)
- CLI entry point (`agent run`, `agent config`)
- LM Studio client with test call
- Playwright launch and basic navigation
- Hardcoded single-task loop (no LLM planning yet)

### Phase 2 — LLM Loop (Week 2)
- Planner prompt + PlanSchema
- Executor loop with ActionSchema
- Screenshot capture + DOM simplifier
- 5 working end-to-end test tasks (Google search, form fill, etc.)

### Phase 3 — Extraction + Output (Week 3)
- Structured data extractor
- Rich terminal table display
- CSV/JSON export
- SQLite run history

### Phase 4 — Polish + Robustness (Week 4)
- Error recovery and retry logic
- Session/cookie persistence for login-required sites
- Cloud model fallback
- `--headless false` debug mode with step-by-step pause
- README and setup guide

---

## Key Files to Create (Claude Code Prompt Order)

1. `pyproject.toml` — dependencies and CLI entrypoint
2. `config.py` — settings dataclass + YAML loader
3. `llm/client.py` — unified LLM client
4. `llm/schemas.py` — Pydantic schemas (PlanSchema, ActionSchema, ResultSchema)
5. `llm/prompts.py` — system prompts
6. `browser/driver.py` — Playwright wrapper
7. `browser/actions.py` — action primitives
8. `browser/extractor.py` — DOM → structured data
9. `agent/observer.py` — page state capture
10. `agent/executor.py` — perception-action loop
11. `agent/planner.py` — task planning
12. `cli/main.py` — Click commands
13. `cli/display.py` — Rich output helpers
14. `storage/runs.py` — SQLite run storage

---

## Example: First Claude Code Prompt

To kick off the build in Claude Code, use this prompt:

```
Build a Python CLI browser automation agent called browseagent.

Stack: Python 3.11, click, playwright (async), pydantic v2, rich, openai SDK.

Start with:
1. pyproject.toml with all dependencies and CLI entrypoint at browseagent.cli.main:app
2. config.py — Settings dataclass loaded from ~/.browseagent/config.yaml
3. llm/schemas.py — Pydantic schemas: PlanSchema, ActionSchema (types: navigate,
   click, type, scroll, extract, done), ObservationSchema, RunResultSchema
4. llm/client.py — LLMClient class that calls OpenAI-compatible API
   (LM Studio at localhost:1234 by default)
5. browser/driver.py — BrowserDriver class wrapping Playwright async API,
   methods: launch(), navigate(url), screenshot(), get_dom_simplified(),
   execute_action(action: ActionSchema)

Use async/await throughout. Include type hints everywhere.
```
