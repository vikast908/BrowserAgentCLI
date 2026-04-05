# BrowseAgent CLI

**Autonomous browser automation from the command line, powered by LLMs.**

BrowseAgent accepts natural language tasks and executes them by autonomously controlling a browser. Describe what you want — the agent plans, navigates, interacts, extracts, and returns structured data. Comes with a **web UI** for live browser viewing and manual takeover control.

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
- [Architecture](#architecture)
- [Engines](#engines)
- [Web UI](#web-ui)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [LLM Providers](#llm-providers)
- [Project Structure](#project-structure)
- [Limitations & Guardrails](#limitations--guardrails)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

- **Natural language input** — describe tasks in plain English
- **Dual engine** — browser-use (batched actions, fast) + crawl4ai (instant extraction)
- **Smart routing** — auto-detects extraction vs interactive tasks, picks the fastest engine
- **Batched actions** — LLM returns up to 10 actions per call instead of 1 (3-10x faster)
- **Web UI dashboard** — live browser view, execution log, manual takeover control
- **Take Control mode** — click and type directly on the browser from the web UI for CAPTCHAs/login
- **Headless or visible** — watch the browser work or run silently in the background
- **Local-first LLM** — runs on Qwen3 via LM Studio (no cloud required)
- **Cloud fallback** — supports Anthropic (Claude) and OpenAI (GPT-4o)
- **Rich terminal UI** — colored output, progress steps, formatted tables
- **Export to CSV/JSON** — save extracted data to files
- **Run history** — SQLite-backed history with replay support

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Interface Layer                                │
│                                                                     │
│  ┌───────────────────┐         ┌──────────────────────────────────┐ │
│  │  CLI (Click)      │         │  Web UI (FastAPI + WebSocket)    │ │
│  │  agent run/ui/    │         │  Live browser view, takeover,    │ │
│  │  history/config   │         │  click/type forwarding           │ │
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
│  │  (auto-detect   │─▶│  (interactive    │  │  (fast extraction │  │
│  │   task type)    │  │   batched agent) │  │   no LLM needed)  │  │
│  └─────────────────┘  └────────┬─────────┘  └───────────────────┘  │
│                                │                                    │
│                     ┌──────────┴──────────┐                         │
│                     │ Batched Actions     │                         │
│                     │ 10 actions per LLM  │                         │
│                     │ call = 3-10x faster │                         │
│                     └──────────┬──────────┘                         │
│                                │                                    │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  LLM Provider    │ │  Browser         │ │  Storage         │
│                  │ │  (Playwright)    │ │                  │
│ LM Studio(local) │ │  Chromium/       │ │  SQLite runs.db  │
│ OpenAI (cloud)   │ │  Firefox/WebKit  │ │  CSV/JSON export │
│ Anthropic(cloud) │ │  CDP protocol    │ │  Run history     │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

---

## Engines

BrowseAgent uses a **dual-engine architecture** for maximum speed:

### browser-use (Interactive Tasks)

Used for tasks that require clicking, typing, navigating, and interacting with web pages.

- **Batched actions** — LLM returns up to 10 actions per inference call, reducing round-trips
- **Message compaction** — compresses conversation history to stay within context limits
- **DOM indexing** — serializes only interactive elements, not the full page
- **Auto-navigation** — detects URLs in tasks and navigates directly
- **Loop detection** — breaks out of repetitive action patterns
- **Error recovery** — retries failed actions with different strategies

```python
# Under the hood, one LLM call returns multiple actions:
# Step 1: navigate → books.toscrape.com, extract titles, done
# vs old approach: 10 separate LLM calls for 10 actions
```

### crawl4ai (Extraction Tasks)

Used for tasks that just need to **extract data** from a URL — no clicking or interaction.

- **Zero LLM calls** — uses CSS/XPath selectors, not LLM per action
- **Sub-second per page** — 10-50x faster than browser-based extraction
- **Auto-detected** — if the task says "get/extract/scrape" + has a URL, crawl4ai runs first

### Smart Router

The engine layer automatically picks the best approach:

```
"extract titles from books.toscrape.com"  → crawl4ai (instant)
"search Google for Python tutorials"      → browser-use (interactive)
"fill out the contact form on example.com" → browser-use (interactive)
```

If crawl4ai doesn't get useful results, it falls back to browser-use automatically.

---

## Web UI

Launch the web dashboard for a visual browser automation experience:

```bash
agent ui
# Opens at http://127.0.0.1:8899
```

### Features

```
┌─────────────────────────────────────────────────────────────────┐
│  BrowseAgent                    CONNECTED   RUNNING    Max: 40  │
├──────────────────────┬──────────────────────────────────────────┤
│                      │                                          │
│  Task Input          │         Live Browser View                │
│  ┌────────────────┐  │                                          │
│  │ your task here │  │    ┌──────────────────────────────┐      │
│  └────────────────┘  │    │                              │      │
│  [Run]               │    │  Real-time screenshot        │      │
│                      │    │  stream from the browser     │      │
│  Plan                │    │                              │      │
│  Goal: ...           │    │  Click and type here         │      │
│  Strategy: ...       │    │  during Take Control mode    │      │
│                      │    │                              │      │
│  Execution Log       │    └──────────────────────────────┘      │
│  Step 1/10: click    │                                          │
│  Step 2/10: type     │    [Take Control] [Pause] [Stop]         │
│  Step 3/10: done     │                                          │
│                      ├──────────────────────────────────────────┤
│  Extracted Data      │  Manual Control Active                   │
│  ┌──────────────┐    │  Click and type directly on browser view │
│  │ title  price │    │  [Resume Automation]                     │
│  │ ...    ...   │    │                                          │
│  └──────────────┘    │                                          │
├──────────────────────┴──────────────────────────────────────────┤
```

### Take Control Mode

When you hit a CAPTCHA, login wall, or need to enter credentials:

1. Click **Take Control** in the browser panel
2. The automation pauses
3. **Click and type directly on the browser view** — your clicks and keystrokes are forwarded to the actual browser via CDP
4. Solve the CAPTCHA, log in, or interact as needed
5. Click **Resume Automation** — the agent continues from where you left off

This works entirely in the web UI — no need to alt-tab to find a browser window.

### Controls

| Button | Action |
|--------|--------|
| **Run** | Start a new task |
| **Take Control** | Pause automation, enable manual interaction |
| **Pause** | Pause the agent mid-execution |
| **Resume** | Continue after pause or takeover |
| **Stop** | Cancel the current task |

---

## How It Works

### For Interactive Tasks (browser-use engine)

```
User Task
    │
    ▼
┌─────────┐     ┌──────────────┐     ┌────────────────────┐
│  Smart   │────▶│  browser-use │────▶│  Playwright Browser │
│  Router  │     │  Agent       │     │  (visible or        │
└─────────┘     │              │     │   headless)          │
                │  Batched     │     └─────────┬────────────┘
                │  LLM calls   │               │
                │  (10 actions │     ┌─────────▼────────────┐
                │   per call)  │     │  Screenshots stream  │
                └──────┬───────┘     │  to Web UI via WS    │
                       │             └──────────────────────┘
                       ▼
                ┌──────────────┐
                │  Results     │
                │  CSV / JSON  │
                │  SQLite      │
                └──────────────┘
```

**Batched action flow** (vs old approach):

```
Old (slow):                          New (fast):
  LLM call → 1 action → execute       LLM call → 10 actions → execute all
  LLM call → 1 action → execute       LLM call → 5 actions  → execute all
  LLM call → 1 action → execute       LLM call → done        → return data
  LLM call → 1 action → execute
  LLM call → 1 action → execute       3 LLM calls total (vs 10+)
  ...                                  3-10x faster
  10+ LLM calls total
```

### For Extraction Tasks (crawl4ai engine)

```
User Task ──▶ crawl4ai ──▶ Fetch page ──▶ Parse HTML ──▶ Return data
                              (httpx)      (no LLM!)      (instant)
```

No browser launched. No LLM calls. Sub-second extraction.

### Error Recovery

- **Action failures** — retried with different selectors
- **Loop detection** — breaks repetitive patterns automatically
- **Timeout handling** — steps capped at 300s, graceful fallback
- **CAPTCHA/login** — pauses for manual takeover via Web UI

---

## Installation

### Prerequisites

- **Python 3.11+**
- **LM Studio** (for local LLM) — download from [lmstudio.ai](https://lmstudio.ai)
- A model loaded in LM Studio with **32K+ context length** (recommended: Qwen3-8B or Qwen3.5-9B)

### Install from source

```bash
git clone https://github.com/vikast908/BrowserAgentCLI.git
cd BrowserAgentCLI
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

Load a model (e.g., Qwen3.5-9B) with **32K+ context length** and start the local server on `localhost:1234`.

### 2. Run your first task (CLI)

```bash
agent run "go to https://books.toscrape.com and get the titles of the first 5 books"
```

### 3. Launch the Web UI

```bash
agent ui
# Open http://127.0.0.1:8899 in your browser
```

### 4. Save results to a file

```bash
agent run "extract the pricing table from stripe.com/pricing" --output pricing.csv
```

### 5. Debug with visible browser

```bash
agent run "fill out the contact form on example.com" --no-headless
```

### 6. Use a cloud model (faster)

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

### `agent ui`

Launch the web UI dashboard.

```bash
agent ui [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--host` | `-h` | Server host | `127.0.0.1` |
| `--port` | `-p` | Server port | `8899` |

### `agent history`

List recent runs.

```bash
agent history [-n 20]
```

### `agent replay <run-id>`

Show details and extracted data from a past run.

```bash
agent replay 41e322d046ae
```

### `agent config`

View or modify configuration.

```bash
agent config get              # Show all settings
agent config get default-model # Show one setting
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

**Important:** Load your model with **32K+ context length** — browser-use's prompts are ~8K tokens.

```bash
agent run "your task"
agent config set lm-studio-url http://localhost:8080
```

**Recommended models:**
- Qwen3.5-9B (best balance of speed and quality)
- Qwen3-8B (lighter, fits in 8GB VRAM)

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
├── engine.py                  # Dual-engine: browser-use + crawl4ai + smart router
│
├── cli/
│   ├── main.py                # Click commands (run, ui, history, config)
│   └── display.py             # Rich terminal UI (tables, spinners, steps)
│
├── ui/
│   ├── server.py              # FastAPI + WebSocket server
│   └── static/
│       ├── index.html         # Split-pane dashboard layout
│       ├── style.css          # Dark theme styling
│       └── app.js             # WebSocket client, click/key forwarding
│
├── agent/                     # Legacy custom agent (kept for reference)
│   ├── planner.py             # LLM task decomposition
│   ├── executor.py            # Custom perception-action loop
│   ├── observer.py            # Page state capture
│   └── memory.py              # Sliding window context manager
│
├── browser/                   # Legacy browser primitives
│   ├── driver.py              # Playwright wrapper
│   ├── actions.py             # Action primitives
│   └── extractor.py           # DOM data extraction
│
├── llm/                       # Legacy LLM layer
│   ├── client.py              # Unified LLM client
│   ├── prompts.py             # System prompts
│   └── schemas.py             # Pydantic models
│
└── storage/
    ├── runs.py                # SQLite run history
    └── export.py              # CSV / JSON export
```

---

## Limitations & Guardrails

| Limitation | Mitigation |
|---|---|
| Sites requiring login | Take Control mode in Web UI — manually log in, then resume |
| CAPTCHAs / bot detection | Take Control mode — solve manually, agent continues |
| Local LLM speed | Use cloud models (Anthropic/OpenAI) for 5-10x faster inference |
| Context length | Load model with 32K+ context in LM Studio |
| Large DOM pages | `max_clickable_elements_length` caps DOM sent to LLM |
| Infinite loops | Built-in loop detection breaks repetitive patterns |
| Extract tool slow | Agent instructed to use `done` action directly instead |

---

## Speed Optimization Tips

| Approach | Speedup | How |
|---|---|---|
| **Use cloud LLM** | 5-10x | `--provider openai --model gpt-4o-mini` (1s/call vs 10-15s local) |
| **Batched actions** | 3-5x | Default with browser-use engine (10 actions per LLM call) |
| **Extraction tasks** | 10-50x | Auto-detected, uses crawl4ai (no LLM needed) |
| **Reduce max steps** | Linear | `--max-steps 10` for simple tasks |
| **Increase context** | Avoids retries | Load model with 32K+ context in LM Studio |

---

## Roadmap

- [ ] **Session management** — `agent login <site>` command to save authenticated cookies
- [ ] **Parallel extraction** — multiple pages open simultaneously
- [ ] **Stagehand integration** — cached selectors for repeatable workflows
- [ ] **Direct HTTP fallback** — skip browser entirely for API-backed sites
- [ ] **Plugin system** — custom extractors for specific sites
- [ ] **MCP integration** — expose as a tool for other AI agents

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11+ | Async ecosystem for AI + browser |
| Browser Agent | browser-use | Batched LLM actions, DOM indexing, error recovery |
| Fast Extraction | crawl4ai | Zero-LLM data extraction via CSS/XPath |
| Browser Engine | Playwright + CDP | Chromium/Firefox/WebKit automation |
| CLI | Click | Argument parsing, help generation |
| Web UI | FastAPI + WebSocket | Real-time dashboard with live browser view |
| Frontend | Vanilla HTML/CSS/JS | Dark theme, split-pane, click forwarding |
| LLM (local) | Qwen3 via LM Studio | OpenAI-compatible API at localhost |
| LLM (cloud) | Claude / GPT-4o | Faster inference for production use |
| Terminal UI | Rich | Tables, spinners, colored output |
| Validation | Pydantic v2 | Structured LLM output schemas |
| Storage | SQLite | Run history and metadata |
| Config | YAML | User settings persistence |

---

## License

MIT
