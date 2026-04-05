# BrowseAgent CLI

**Autonomous browser automation from the command line, powered by LLMs.**

BrowseAgent accepts natural language tasks and executes them by autonomously controlling a headless browser. Describe what you want — the agent plans, navigates, interacts, extracts, and returns structured data.

```
$ agent run "go to books.toscrape.com and get titles of the first 5 books"

  ◎ Planning task...
    Goal: Extract titles of the first 5 books from books.toscrape.com
    Strategy: Navigate to homepage, locate book listings, extract titles
    Start URL: https://books.toscrape.com/
    Estimated steps: 5

  ◎ Step 1/8 → click → a
  ◎ Step 2/8 → extract → a
  ◎ Step 3/8 → done

  ✓ Task complete in 3 steps (30.3s)
    Extracted 5 items

┌───────────────────────────────────────┐
│ title                                 │
├───────────────────────────────────────┤
│ A Light in the Attic                  │
│ Tipping the Velvet                    │
│ Soumission                            │
│ Sharp Objects                         │
│ Sapiens: A Brief History of Humankind │
└───────────────────────────────────────┘

  Saved to: books.csv
```

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [LLM Providers](#llm-providers)
- [Project Structure](#project-structure)
- [Module Reference](#module-reference)
- [Limitations & Guardrails](#limitations--guardrails)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

- **Natural language input** — describe tasks in plain English
- **Autonomous planning** — LLM decomposes tasks into browser steps
- **Headless browser control** — Playwright-powered Chromium, Firefox, or WebKit
- **Structured data extraction** — tables, lists, links parsed from DOM
- **Local-first LLM** — runs on Qwen3-8B via LM Studio (no cloud required)
- **Cloud fallback** — supports Anthropic (Claude) and OpenAI (GPT-4o)
- **Rich terminal UI** — colored output, progress steps, formatted tables
- **Export to CSV/JSON** — save extracted data to files
- **Run history** — SQLite-backed history with replay support
- **Cookie persistence** — authenticated sessions for login-required sites
- **Vision + DOM hybrid** — screenshots and simplified DOM for accurate decisions

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                               │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  main.py    │  │  display.py  │  │  Click Commands        │  │
│  │  (commands) │  │  (Rich UI)   │  │  run/history/config    │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────────┘  │
│         │                │                                      │
└─────────┼────────────────┼──────────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Layer                              │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  planner.py │  │ executor.py  │  │  memory.py             │  │
│  │  (task      │  │ (perception- │  │  (sliding window       │  │
│  │   planning) │  │  action loop)│  │   context manager)     │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────────┘  │
│         │                │                                      │
│         │         ┌──────┴───────┐                               │
│         │         │ observer.py  │                               │
│         │         │ (page state  │                               │
│         │         │  capture)    │                               │
│         │         └──────┬───────┘                               │
└─────────┼────────────────┼──────────────────────────────────────┘
          │                │
          ▼                ▼
┌──────────────────┐ ┌────────────────────────────────────────────┐
│    LLM Layer     │ │              Browser Layer                 │
│                  │ │                                            │
│ ┌──────────────┐ │ │ ┌────────────┐ ┌──────────┐ ┌───────────┐ │
│ │  client.py   │ │ │ │ driver.py  │ │actions.py│ │extractor  │ │
│ │  (unified    │ │ │ │ (Playwright│ │(typed    │ │.py (DOM   │ │
│ │   LLM API)  │ │ │ │  wrapper)  │ │ action   │ │ data      │ │
│ │              │ │ │ │            │ │ prims)   │ │ parsing)  │ │
│ ├──────────────┤ │ │ └─────┬──────┘ └──────────┘ └───────────┘ │
│ │  prompts.py  │ │ │       │                                   │
│ │  (system     │ │ │       ▼                                   │
│ │   prompts)   │ │ │  ┌─────────────────────────────────┐      │
│ ├──────────────┤ │ │  │  Chromium / Firefox / WebKit    │      │
│ │  schemas.py  │ │ │  │  (headless or visible)          │      │
│ │  (Pydantic   │ │ │  └─────────────────────────────────┘      │
│ │   models)    │ │ │                                            │
│ └──────────────┘ │ └────────────────────────────────────────────┘
└──────────────────┘
          │
          ▼
┌──────────────────┐
│  Storage Layer   │
│                  │
│ ┌──────────────┐ │    ┌──────────────────────────────────┐
│ │  runs.py     │ │    │  ~/.browseagent/                 │
│ │  (SQLite)    │─┼───▶│  ├── config.yaml                 │
│ ├──────────────┤ │    │  └── runs/                       │
│ │  export.py   │ │    │      ├── runs.db                 │
│ │  (CSV/JSON)  │ │    │      └── <run-id>/results.json   │
│ └──────────────┘ │    └──────────────────────────────────┘
└──────────────────┘
```

---

## How It Works

The agent follows a 6-phase pipeline for every task:

```
 User Task ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5 ──▶ Phase 6
  (string)     PLAN        LAUNCH      OBSERVE     DECIDE +     EXTRACT     OUTPUT
               (LLM)      (Browser)    (DOM +       ACT         (data)     (table +
                                       screenshot)  (loop)                  export)
```

### Phase 1 — Task Planning (LLM Call #1)

The task string is sent to the LLM with a planner prompt. The model returns a structured plan:

```json
{
  "goal": "Find 10 software engineer leads from LinkedIn in Mumbai",
  "steps_estimate": 12,
  "first_url": "https://www.linkedin.com/search/results/people/",
  "plan_summary": "Search LinkedIn, apply location filter, extract profile data"
}
```

### Phase 2 — Browser Launch

Playwright launches a Chromium instance (headless by default) with a realistic user agent and 1280x800 viewport. Navigates to the `first_url` from the plan.

### Phase 3 — Observe Page State

Each loop iteration captures a snapshot of the current page:

- **Simplified DOM** — visible text, links, buttons, inputs, headings (not raw HTML)
- **Screenshot** — optional base64 PNG for vision-capable models
- **URL + title** — current page metadata

The DOM simplification extracts up to 200 elements in a structured format:

```
[link] "Learn more" → a[href="https://example.com"]
[button] "Search" → #search-btn
[input:text] "query" (current: "") → input[name="q"]
[h1] "Welcome to Example"
[text] "This is a paragraph of content..."
```

### Phase 4 — Decide + Act (LLM Call #2...N)

The LLM receives the observation and decides the next action:

```json
{
  "action": "type",
  "target": "input[name='q']",
  "value": "software engineer Mumbai",
  "reasoning": "Need to enter the search query",
  "confidence": 0.95
}
```

Available actions:

| Action | Description | Playwright Call |
|--------|-------------|-----------------|
| `navigate` | Go to a URL | `page.goto(url)` |
| `click` | Click an element | `page.click(selector)` |
| `type` | Type into an input | `page.fill(selector, value)` |
| `press` | Press a keyboard key | `page.keyboard.press(key)` |
| `scroll` | Scroll up or down | `page.evaluate("window.scrollBy()")` |
| `select` | Pick a dropdown option | `page.select_option(selector, value)` |
| `extract` | Pull data from DOM | DOM parser or LLM extraction |
| `wait` | Wait for page load | `page.wait_for_load_state("networkidle")` |
| `done` | Task complete | Returns extracted data |

### Phase 5 — Data Extraction

When the LLM determines the task is complete, it returns structured data directly in the `done` action. Alternatively, the `extract` action triggers DOM-based extraction using CSS selectors.

### Phase 6 — Output & Export

Results are displayed as a Rich table in the terminal. Data is saved to SQLite for history and optionally exported to CSV or JSON.

### Error Recovery

- If a selector is not found, the agent retries with a different approach
- After 2 consecutive failures on the same target, the step is skipped
- The full error context is fed back to the LLM for self-correction

```
Perception-Action Loop Detail:

    ┌────────────┐
    │  Observe   │◄──────────────────────────────┐
    │  (DOM +    │                               │
    │  screenshot│                               │
    └─────┬──────┘                               │
          │                                      │
          ▼                                      │
    ┌────────────┐                               │
    │  Decide    │                               │
    │  (LLM call)│                               │
    └─────┬──────┘                               │
          │                                      │
          ▼                                      │
    ┌────────────┐    ┌────────┐                 │
    │  action == ├───▶│ Return │                 │
    │  "done"?   │yes │ data   │                 │
    └─────┬──────┘    └────────┘                 │
          │ no                                   │
          ▼                                      │
    ┌────────────┐                               │
    │  Execute   │                               │
    │  (browser  │───────────────────────────────┘
    │   action)  │
    └────────────┘
```

---

## Installation

### Prerequisites

- **Python 3.11+**
- **LM Studio** (for local LLM) — download from [lmstudio.ai](https://lmstudio.ai)
- A model loaded in LM Studio (recommended: Qwen3-8B or similar)

### Install from source

```bash
git clone https://github.com/your-username/browseagent.git
cd browseagent
pip install -e .
playwright install chromium
```

### Verify installation

```bash
agent --version
agent --help
```

---

## Quick Start

### 1. Start LM Studio

Load a model (e.g., Qwen3-8B) and start the local server on `localhost:1234`.

### 2. Run your first task

```bash
agent run "go to https://books.toscrape.com and get the titles and prices of the first 5 books"
```

### 3. Save results to a file

```bash
agent run "extract the pricing table from stripe.com/pricing" --output pricing.csv
```

### 4. Debug with visible browser

```bash
agent run "fill out the contact form on example.com" --no-headless
```

### 5. Use a cloud model

```bash
export ANTHROPIC_API_KEY=sk-ant-...
agent run "search for Python tutorials" --provider anthropic --model claude-sonnet-4-20250514
```

---

## CLI Reference

### `agent run <task>`

Execute a browser automation task.

```bash
agent run "your task description" [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--model` | `-m` | LLM model name | `qwen3-8b` |
| `--provider` | `-p` | LLM provider (`lm_studio`, `openai`, `anthropic`) | `lm_studio` |
| `--output` | `-o` | Export results to file (`.csv` or `.json`) | None |
| `--headless / --no-headless` | | Show/hide browser window | `--headless` |
| `--max-steps` | | Cap execution steps | `40` |
| `--screenshot` | | Save screenshots of each step | `false` |

### `agent history`

List recent runs.

```bash
agent history [-n 20]
```

```
┌──────────────┬───────────────────┬───────────┬───────┬───────┬─────────────┐
│ Run ID       │ Task              │ Status    │ Steps │ Time  │ Date        │
├──────────────┼───────────────────┼───────────┼───────┼───────┼─────────────┤
│ 41e322d046ae │ go to books.to... │ completed │ 3     │ 30.3s │ 2026-04-05  │
│ 8f2a1bc93d01 │ extract pricing.. │ completed │ 7     │ 45.1s │ 2026-04-04  │
└──────────────┴───────────────────┴───────────┴───────┴───────┴─────────────┘
```

### `agent replay <run-id>`

Show details and extracted data from a past run.

```bash
agent replay 41e322d046ae
```

### `agent config`

View or modify configuration.

```bash
# Show all settings
agent config get

# Show a specific setting
agent config get default-model

# Change a setting
agent config set default-model qwen3-8b
agent config set headless false
agent config set max-steps 30
```

---

## Configuration

Settings are stored in `~/.browseagent/config.yaml`:

```yaml
default_provider: lm_studio
lm_studio_url: http://localhost:1234
default_model: qwen3-8b
headless: true
max_steps: 40
screenshot: false
browser: chromium          # chromium | firefox | webkit
data_dir: ~/.browseagent/runs
```

### Priority order

CLI flags > config.yaml > defaults

### API keys

API keys are loaded from environment variables (never saved to disk):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
```

---

## LLM Providers

### LM Studio (Local, Default)

Runs locally via an OpenAI-compatible API. No data leaves your machine.

```bash
# Default — uses LM Studio at localhost:1234
agent run "your task"

# Custom URL
agent config set lm-studio-url http://localhost:8080
```

**Recommended models:**
- Qwen3-8B (4-bit, fits in 8GB VRAM)
- Qwen3.5-9B
- Any model with strong instruction following and JSON output

### Anthropic (Claude)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
agent run "your task" --provider anthropic --model claude-sonnet-4-20250514
```

### OpenAI (GPT-4o)

```bash
export OPENAI_API_KEY=sk-...
agent run "your task" --provider openai --model gpt-4o
```

---

## Project Structure

```
browseagent/
├── __init__.py                # Package version
├── config.py                  # Settings dataclass + YAML loader
│
├── cli/
│   ├── main.py                # Click commands (run, history, config)
│   └── display.py             # Rich terminal UI (tables, spinners, steps)
│
├── agent/
│   ├── planner.py             # LLM task decomposition → PlanSchema
│   ├── executor.py            # Core observe → decide → act loop
│   ├── observer.py            # Page state capture (DOM + screenshot)
│   └── memory.py              # Sliding window context manager
│
├── browser/
│   ├── driver.py              # Playwright wrapper (launch, navigate, act)
│   ├── actions.py             # Standalone action primitives
│   └── extractor.py           # DOM → structured data extraction
│
├── llm/
│   ├── client.py              # Unified LLM client (local + cloud)
│   ├── prompts.py             # Planner & executor system prompts
│   └── schemas.py             # Pydantic models (Plan, Action, Observation)
│
└── storage/
    ├── runs.py                # SQLite run history
    └── export.py              # CSV / JSON export
```

---

## Module Reference

### config.py

| Symbol | Type | Description |
|--------|------|-------------|
| `Settings` | dataclass | Runtime configuration with defaults |
| `load_settings()` | function | Load from `~/.browseagent/config.yaml` |
| `save_settings()` | function | Persist to YAML (excludes API keys) |

### llm/schemas.py

| Schema | Fields | Description |
|--------|--------|-------------|
| `ActionType` | enum | 9 action types (navigate, click, type, press, scroll, select, extract, wait, done) |
| `PlanSchema` | goal, steps_estimate, first_url, plan_summary | Task plan from planner LLM |
| `ActionSchema` | action, target, value, reasoning, confidence, data | Single action from executor LLM |
| `ObservationSchema` | url, title, dom_text, screenshot_b64, timestamp | Page state snapshot |
| `StepRecord` | step_number, observation, action, success, error | Full step trace |
| `RunResultSchema` | run_id, task, plan, steps, data, status, timing | Complete run result |

### llm/client.py

| Symbol | Description |
|--------|-------------|
| `LLMClient` | Unified async client for LM Studio, OpenAI, and Anthropic |
| `chat()` | Send messages, optionally request JSON output |
| `chat_structured()` | Chat and return validated Pydantic model (with retries) |
| `_extract_json()` | Strip `<think>` tags, code fences, find JSON in raw output |

### browser/driver.py

| Method | Description |
|--------|-------------|
| `launch()` | Start Playwright + browser with configured viewport/user-agent |
| `navigate(url)` | Go to URL, wait for DOM content loaded |
| `screenshot()` | Capture page as base64 PNG |
| `get_dom_simplified()` | Extract links, buttons, inputs, headings, text (up to 200 elements) |
| `execute_action(action)` | Map ActionSchema to Playwright call |
| `load_cookies() / save_cookies()` | Persist authenticated sessions |

### agent/executor.py

| Symbol | Description |
|--------|-------------|
| `AgentExecutor` | Orchestrates the full plan → launch → loop → export pipeline |
| `run(task)` | Execute a complete agent run, returns RunResultSchema |
| `on_plan / on_step / on_error` | Callbacks for CLI display integration |

### storage/runs.py

| Method | Description |
|--------|-------------|
| `RunStore.save_run()` | Insert run to SQLite + save results.json |
| `RunStore.list_runs()` | Recent runs sorted by date |
| `RunStore.get_run()` | Full run details by ID |

---

## Limitations & Guardrails

| Limitation | Mitigation |
|---|---|
| Sites requiring login (LinkedIn, etc.) | Pre-login via `load_cookies()`; cookie persistence |
| CAPTCHAs / bot detection | Flagged to user; agent pauses with `wait` action |
| Dynamic JS-heavy SPAs | Playwright waits for `networkidle` before observation |
| LLM hallucinating selectors | DOM simplifier provides real selectors; validation before click |
| Local LLM JSON reliability | `json_schema` response format + retry with stricter prompt |
| Infinite scroll / pagination | `max-steps` cap; smart "load more" detection |
| Large DOM pages | Truncated to 6000 chars to fit LLM context window |

---

## Roadmap

- [ ] **Session management** — `agent login <site>` command to save authenticated cookies
- [ ] **Step-by-step debug mode** — pause between steps in `--no-headless` mode
- [ ] **Parallel extraction** — multiple pages open simultaneously
- [ ] **Plugin system** — custom extractors for specific sites
- [ ] **Proxy support** — rotate IPs for large-scale scraping
- [ ] **PDF / screenshot export** — save full-page renders per step
- [ ] **MCP integration** — expose as a tool for other AI agents

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11+ | Async ecosystem for AI + browser |
| CLI | Click | Argument parsing, help generation |
| Browser | Playwright (async) | Headless Chromium/Firefox/WebKit |
| LLM (local) | Qwen3-8B via LM Studio | OpenAI-compatible API at localhost |
| LLM (cloud) | Claude / GPT-4o | Higher-quality planning & vision |
| Terminal UI | Rich | Tables, spinners, colored output |
| Validation | Pydantic v2 | Structured LLM output schemas |
| Storage | SQLite | Run history and metadata |
| Config | YAML | User settings persistence |

---

## License

MIT
