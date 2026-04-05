# BrowseAgent CLI

**Autonomous browser automation from the command line, powered by LLMs.**

BrowseAgent accepts natural language tasks and executes them by autonomously controlling a browser. Describe what you want — the agent plans, navigates, interacts, extracts, and returns structured data. Comes with a **web UI dashboard** for live browser viewing and manual takeover.

```
$ agent run "go to books.toscrape.com and get titles of the first 5 books"

  * Planning task...
  * Launching browser...

  Step 1/10: navigate → https://books.toscrape.com
  Step 2/10: extract, done

  Task complete in 2 steps (18.4s)
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
- [Web UI](#web-ui)
- [Architecture](#architecture)
- [Engines](#engines)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [LLM Providers](#llm-providers)
- [Project Structure](#project-structure)
- [Speed Tips](#speed-tips)
- [Limitations](#limitations)
- [Roadmap](#roadmap)

---

## Features

- **Natural language input** — describe tasks in plain English
- **Dual engine** — `browser-use` for interactive tasks + `crawl4ai` for instant extraction
- **Smart routing** — auto-detects task type, picks the fastest engine
- **Batched actions** — LLM returns up to 10 actions per call (3-10x faster than single-action loops)
- **Web UI dashboard** — live browser view, execution log, interactive manual control
- **Take Control mode** — click and type directly on the browser view for CAPTCHAs and login
- **Local-first LLM** — runs on Qwen3 via LM Studio (no cloud required, no data leaves your machine)
- **Cloud support** — Anthropic (Claude) and OpenAI (GPT-4o) for faster inference
- **Rich terminal output** — colored steps, formatted tables, progress indicators
- **Export** — save extracted data to CSV or JSON
- **Run history** — SQLite-backed history with `agent history` and `agent replay`
- **Configurable** — YAML config at `~/.browseagent/config.yaml`, CLI flags override everything

---

## Web UI

Launch the web dashboard with `agent ui` and open `http://127.0.0.1:8899`:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ◉ BrowseAgent  v0.1.0       ● CONNECTED  ● RUNNING         Max Steps [40] │
├────────────────────────┬─────────────────────────────────────────────────────┤
│                        │  Browser View          [✋ Take Control] [⏸] [⏹]  │
│  ┌──────────────────┐  │  ┌─────────────────────────────────────────────┐   │
│  │ Describe your    │  │  │                                             │   │
│  │ task here...     │  │  │                                             │   │
│  └──────────────────┘  │  │         Live browser screenshot             │   │
│  [▶ Run]               │  │         stream via WebSocket                │   │
│                        │  │                                             │   │
│  ┌─ Plan ────────────┐ │  │         Click here to interact             │   │
│  │ Goal: Extract...  │ │  │         during Take Control mode           │   │
│  │ Strategy: Nav...  │ │  │                                             │   │
│  │ URL: https://...  │ │  │                                             │   │
│  │ Est. steps: 5     │ │  │                                             │   │
│  └───────────────────┘ │  └─────────────────────────────────────────────┘   │
│                        │                                                    │
│  ┌─ Execution Log ──┐ │  ┌─ Takeover Banner ──────────────────────────────┐ │
│  │ ○ Connected       │ │  │ ✋ Manual Control Active — Click and type     │ │
│  │ ✓ Plan ready      │ │  │ directly on the browser view above           │ │
│  │ ◎ Step 1 → click  │ │  │                        [▶ Resume Automation] │ │
│  │ ◎ Step 2 → type   │ │  └──────────────────────────────────────────────┘ │
│  │ ◎ Step 3 → done   │ │                                                    │
│  │ ✓ Complete (18s)  │ │                                                    │
│  └───────────────────┘ │                                                    │
│                        │                                                    │
│  ┌─ Extracted Data ──┐ │                                                    │
│  │ title       price │ │                                                    │
│  │ Book A      £51   │ │                                                    │
│  │ Book B      £53   │ │                                                    │
│  └───────────────────┘ │                                                    │
├────────────────────────┴─────────────────────────────────────────────────────┤
```

### UI Layout

- **Top bar** — connection status, agent state badge (Idle/Running/Paused/Manual Control), max steps control
- **Left panel** — task input textarea, plan card, scrollable execution log, extracted data table
- **Right panel** — live browser screenshot stream, control buttons (Take Control, Pause, Stop)
- **Divider** — draggable to resize left/right panels
- **Dark theme** — designed for extended use

### Take Control Mode

When you encounter a CAPTCHA, login wall, or need to enter credentials:

1. Click **Take Control** in the browser panel header
2. Automation pauses, the banner appears at the bottom
3. **Click directly on the browser screenshot** — clicks are mapped to browser coordinates and forwarded via CDP
4. **Type on the browser view** — keystrokes (letters, Enter, Backspace, Tab, arrows) are forwarded to the page
5. A **yellow ripple effect** shows where you clicked
6. Click **Resume Automation** when done — the agent continues where it left off

### Controls

| Button | Action |
|--------|--------|
| **Run** | Start a new task (or press Enter in the textarea) |
| **Take Control** | Pause automation, enable direct mouse/keyboard interaction |
| **Pause / Resume** | Pause/continue the agent mid-execution |
| **Stop** | Cancel the current task |
| **Clear** | Clear the execution log |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Interface Layer                                │
│                                                                     │
│  ┌───────────────────┐         ┌──────────────────────────────────┐ │
│  │  CLI (Click)      │         │  Web UI (FastAPI + WebSocket)    │ │
│  │  agent run/ui/    │         │  Live screenshots, click/key    │ │
│  │  history/config   │         │  forwarding, takeover control   │ │
│  └────────┬──────────┘         └──────────────┬───────────────────┘ │
│           │                                   │                     │
└───────────┼───────────────────────────────────┼─────────────────────┘
            │                                   │
            ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Engine Layer (engine.py)                      │
│                                                                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  Smart Router   │  │  browser-use     │  │  crawl4ai         │  │
│  │  run_task()     │─▶│  Batched actions  │  │  Zero-LLM extract │  │
│  │  auto-detect    │  │  10 per LLM call │  │  sub-second/page  │  │
│  └─────────────────┘  └────────┬─────────┘  └───────────────────┘  │
│                                │                                    │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  LLM Provider    │ │  Playwright      │ │  Storage         │
│                  │ │  + CDP           │ │                  │
│ LM Studio(local) │ │  Chromium/       │ │  SQLite runs.db  │
│ OpenAI (cloud)   │ │  Firefox/WebKit  │ │  CSV/JSON export │
│ Anthropic(cloud) │ │  1280x800        │ │  results.json    │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

---

## Engines

### browser-use (Interactive Tasks)

Powers tasks that require clicking, typing, navigating, filling forms, and interacting with web pages. Based on the [browser-use](https://github.com/browser-use/browser-use) library.

Key capabilities:
- **Batched actions** — LLM returns multiple actions per inference call, cutting round-trips by 3-10x
- **Message compaction** — compresses conversation history to fit within context limits
- **DOM indexing** — serializes only interactive elements (not full HTML)
- **Loop detection** — automatically breaks repetitive action patterns
- **Error recovery** — retries failed actions with different strategies
- **Auto-navigation** — detects URLs in task description and navigates directly

### crawl4ai (Extraction Tasks)

Powers tasks that only need to **read data from a URL** — no clicking or form filling required. Based on [crawl4ai](https://github.com/unclecode/crawl4ai).

Key capabilities:
- **Zero LLM calls** — parses HTML directly, no per-action inference
- **Sub-second per page** — 10-50x faster than browser-based loops
- **Markdown conversion** — extracts clean text from any page

### Smart Router (`run_task()`)

The CLI uses a smart router that picks the fastest engine automatically:

| Task pattern | Engine | Why |
|---|---|---|
| `"extract titles from books.toscrape.com"` | crawl4ai | Has URL + extraction keywords, no interaction needed |
| `"scrape prices from example.com/products"` | crawl4ai | Pure data extraction |
| `"search Google for Python tutorials"` | browser-use | Requires typing + navigation |
| `"fill out the contact form on example.com"` | browser-use | Requires interaction |

If crawl4ai doesn't return useful results, it falls back to browser-use automatically.

> **Note:** The Web UI currently routes all tasks through browser-use directly (skipping crawl4ai) to ensure the live browser view always works.

---

## How It Works

### Interactive Task Flow (browser-use)

```
 User Task
     │
     ▼
 Smart Router ──▶ browser-use Agent
                      │
                      ├── LLM Call #1 → [navigate, click, type] → execute all 3
                      ├── LLM Call #2 → [scroll, extract, done]  → execute all 3
                      │
                      ▼
                  Return results (3-10x fewer LLM calls than single-action loops)
```

### Extraction Task Flow (crawl4ai)

```
 User Task ──▶ crawl4ai ──▶ Fetch page ──▶ Parse HTML ──▶ Return data
                              (no browser)   (no LLM)       (instant)
```

---

## Installation

### Prerequisites

- **Python 3.11+**
- **LM Studio** (for local LLM) — [lmstudio.ai](https://lmstudio.ai)
- A model loaded with **32K+ context length** (browser-use prompts are ~8K tokens)

### Install from source

```bash
git clone https://github.com/vikast908/BrowserAgentCLI.git
cd BrowserAgentCLI
pip install -e .
playwright install chromium
```

### Verify

```bash
agent --version
agent --help
```

---

## Quick Start

### 1. Start LM Studio

Load a model (recommended: **Qwen3.5-9B**) with **32K+ context length**. Start the local server on `localhost:1234`.

### 2. Run a task (CLI)

```bash
agent run "go to https://books.toscrape.com and get the titles of the first 5 books"
```

### 3. Launch the Web UI

```bash
agent ui
# Open http://127.0.0.1:8899 in your browser
```

### 4. Export results

```bash
agent run "extract the pricing table from stripe.com/pricing" --output pricing.csv
```

### 5. Visible browser (debug mode)

```bash
agent run "fill out the form on example.com" --no-headless
```

### 6. Use a cloud model

```bash
export OPENAI_API_KEY=sk-...
agent run "search for Python tutorials" --provider openai --model gpt-4o
```

---

## CLI Reference

### `agent run <task>`

Execute a browser automation task.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--model` | `-m` | LLM model name | from config |
| `--provider` | `-p` | `lm_studio`, `openai`, `anthropic` | `lm_studio` |
| `--output` | `-o` | Export to `.csv` or `.json` | None |
| `--headless / --no-headless` | | Show/hide browser | `--headless` |
| `--max-steps` | | Step limit | `40` |
| `--screenshot` | | Save step screenshots | off |

### `agent ui`

Launch the web dashboard.

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--host` | `-h` | Server bind address | `127.0.0.1` |
| `--port` | `-p` | Server port | `8899` |

### `agent history [-n 20]`

List recent runs with status, step count, and elapsed time.

### `agent replay <run-id>`

Show details and extracted data from a past run.

### `agent config get [key]`

Show all settings or a specific one. API keys are masked.

### `agent config set <key> <value>`

Persist a setting. Keys use hyphens: `agent config set default-model qwen3-8b`.

---

## Configuration

Stored at `~/.browseagent/config.yaml`:

```yaml
default_provider: lm_studio
lm_studio_url: http://localhost:1234
default_model: qwen3-8b
headless: true
max_steps: 40
screenshot: false
browser: chromium
data_dir: ~/.browseagent/runs
```

**Priority:** CLI flags > config.yaml > defaults

**API keys** are loaded from environment variables (never written to disk):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
```

---

## LLM Providers

### LM Studio (Local, Default)

No data leaves your machine. **Important:** Load your model with **32K+ context length**.

```bash
agent run "your task"
agent config set lm-studio-url http://localhost:8080
```

Recommended models: **Qwen3.5-9B**, Qwen3-8B

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
agent run "your task" --provider openai --model gpt-4o
```

### Anthropic

```bash
export ANTHROPIC_API_KEY=sk-ant-...
agent run "your task" --provider anthropic --model claude-sonnet-4-20250514
```

---

## Project Structure

```
browseagent/
├── __init__.py              # Package metadata (v0.1.0)
├── config.py                # Settings dataclass, YAML loader/saver
├── engine.py                # Dual-engine layer: browser-use + crawl4ai + smart router
│
├── cli/
│   ├── main.py              # Click commands: run, ui, history, replay, config
│   └── display.py           # Rich terminal formatting (tables, steps, status)
│
├── ui/
│   ├── server.py            # FastAPI app, WebSocket handler, CDP mouse/key forwarding
│   └── static/
│       ├── index.html       # Split-pane layout, takeover input layer
│       ├── style.css        # Dark theme, badges, responsive design
│       └── app.js           # WebSocket client, coordinate mapping, ripple effects
│
├── storage/
│   ├── runs.py              # RunStore — SQLite run history + results.json per run
│   └── export.py            # CSV and JSON exporters
│
├── llm/
│   └── schemas.py           # Pydantic models (RunResultSchema used for storage)
│
├── agent/                   # Legacy custom agent (kept for reference)
├── browser/                 # Legacy Playwright wrapper (kept for reference)
└── llm/client.py, prompts.py  # Legacy LLM layer (kept for reference)
```

### Key Files

| File | Purpose |
|------|---------|
| `engine.py` | Core engine — `run_task()` routes to browser-use or crawl4ai |
| `cli/main.py` | All CLI commands, wires callbacks to Rich display |
| `ui/server.py` | FastAPI + WebSocket, screenshot streaming, CDP click/key forwarding |
| `ui/static/app.js` | Frontend logic: WebSocket, coordinate mapping, takeover interaction |
| `config.py` | Settings from `~/.browseagent/config.yaml` with env var fallbacks |
| `storage/runs.py` | SQLite history: save, list, get runs |

---

## Speed Tips

| Approach | Speedup | How |
|---|---|---|
| **Cloud LLM** | 5-10x | `--provider openai --model gpt-4o-mini` (~1s/call vs 10-15s local) |
| **Extraction tasks** | 10-50x | Auto-detected by smart router, uses crawl4ai (no LLM) |
| **Batched actions** | 3-5x | Default: browser-use returns 10 actions per LLM call |
| **Fewer steps** | Linear | `--max-steps 10` for simple tasks |
| **32K+ context** | Avoids crashes | Load model with higher context in LM Studio |

---

## Limitations

| Issue | Mitigation |
|---|---|
| Sites requiring login | Take Control in Web UI — log in manually, then resume |
| CAPTCHAs | Take Control — solve it, agent continues |
| Local LLM speed | Use cloud models for 5-10x faster inference |
| Context too small | Load model with 32K+ context in LM Studio |
| Large pages | `max_clickable_elements_length` caps DOM sent to LLM |
| Agent loops | Built-in loop detection breaks repetitive patterns |

---

## Roadmap

- [ ] Session management — `agent login <site>` to save authenticated cookies
- [ ] Parallel extraction — multiple pages simultaneously
- [ ] Stagehand integration — cached selectors for repeatable workflows
- [ ] Direct HTTP fallback — skip browser for API-backed sites
- [ ] Plugin system — custom extractors for specific sites
- [ ] MCP integration — expose as a tool for other AI agents

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Browser Agent | [browser-use](https://github.com/browser-use/browser-use) — batched LLM actions, DOM indexing |
| Fast Extraction | [crawl4ai](https://github.com/unclecode/crawl4ai) — zero-LLM scraping |
| Browser | Playwright + Chrome DevTools Protocol |
| CLI | Click |
| Web UI | FastAPI, WebSocket, vanilla JS |
| Terminal | Rich |
| Validation | Pydantic v2 |
| Storage | SQLite |
| Config | YAML |
| LLM (local) | Qwen3 via LM Studio |
| LLM (cloud) | Claude, GPT-4o |
