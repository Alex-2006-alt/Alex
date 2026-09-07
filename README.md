# A.L.E.X — Advanced Linguistic Executive System

> A personal AI assistant for Windows that listens, talks, controls your PC, and
> plans multi-step work on its own.

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure
```bash
copy .env.example .env
```
Then set at least one LLM key in `.env`. A free Gemini key from
https://aistudio.google.com/apikey is the fastest way to start:
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

### 3. Run

```bash
# Web interface (recommended — opens in your browser)
python main.py --server

# Text-only, type commands in the terminal
python main.py --text

# Voice, wake word "Hey Alex"
python main.py

# Voice, always listening
python main.py --no-wake-word

# Diagnostics — config, logger, TTS, audio devices, LLM connectivity
python main.py --test
```

---

## How a request flows

Every mode funnels into the same pipeline. The first three stages are free —
only stage 4 costs an LLM call.

```
  listen  ──►  special commands  ──►  dispatcher  ──►  Brain  ──►  speak / return
  (voice,      (built-ins, no       (prefix match,   (LLM)
   text,        LLM: status,         no LLM:
   HTTP)        clear history,       say_time,
                cancel tasks)        open_url, run)
                                                       │
                                      ┌────────────────┴────────────────┐
                                      │                                 │
                                 fast path                        agentic path
                            one call, one action           Planner decomposes the
                                      │                    goal into steps, runs
                                      │                    them, reflects, and
                                      │                    iterates if unfinished
                                      └────────────┬────────────────────┘
                                                   ▼
                                            ToolRegistry
                                     34 tools, safety-gated
```

`Planner.should_plan()` decides which path a request takes: conversation and
short questions stay on the fast path; requests with multiple actions, or over
25 words, go agentic.

---

## Features

### AI Brain
- **Four providers**: Gemini, OpenAI, OpenRouter (200+ models, free tier), and
  Ollama for fully local operation.
- **Agentic planning**: complex goals are decomposed into a dependency graph of
  steps, executed (in parallel where independent), then reflected on. If the
  goal isn't met, reflection adds steps and the loop runs again — up to
  `MAX_AGENT_ITERATIONS`.
- **Step chaining**: a step can consume an earlier one's output by writing
  `{{step_1.result}}` in any parameter.
- **Long-term memory**: SQLite-backed facts, preferences and task history, with
  optional semantic recall via sentence-transformers.
- **Context awareness**: active window, time of day and username are injected
  into every prompt.
- **Retries**: empty or failed LLM responses retry with backoff; rate limits
  (429) back off harder.

### Voice
- **Whisper STT** — local, no API key needed.
- **pyttsx3 TTS** — offline speech.
- **Wake word** — "Hey Alex", detected with a Whisper tiny model.

### Tools (34, in 6 categories)

Tools are registered with the `@tool` decorator and described to the LLM from
the live registry, so the prompt can never drift out of sync with what exists.

| Category | Tools |
|---|---|
| **web** | `web_search` (DuckDuckGo), `web_open`, `web_scrape` |
| **files** | `file_read`, `file_write`, `file_find`, `file_list`, `file_move`, `file_copy`, `file_delete`, `file_mkdir` |
| **system** | `app_open`, `app_close`, `process_list`, `process_kill`, `system_volume`, `system_power`, `screenshot_capture`, `keyboard_type`, `keyboard_press`, `clipboard_op`, `media_play` |
| **code** | `code_run`, `code_evaluate`, `shell_run` |
| **data** | `data_read_csv`, `data_write_csv`, `data_read_json`, `data_write_json`, `data_analyze` |
| **notifications** | `notify`, `reminder_set`, `weather_get`, `email_send` |

### Background work
- **TaskManager** runs timers and long jobs off the main thread.
- **SystemMonitor** watches CPU, RAM and disk, and raises spoken + desktop
  alerts on threshold breaches.

### Web interface
Holographic dark-mode HUD: live system stats, animated AI core, plan and task
panels, memory browser, and approval cards for dangerous actions. Works
standalone in demo mode, or with the full backend.

---

## Safety model

Every tool declares a safety level, and `ToolRegistry` enforces it.

| Level | Meaning | Tools |
|---|---|---|
| `SAFE` | Runs immediately | most |
| `WARN` | Runs, logs a warning | `file_write`, `file_move`, `app_close` |
| `CONFIRM` | **Requires explicit approval** | `shell_run`, `code_run`, `file_delete`, `process_kill`, `system_power` |

A `CONFIRM` tool is **denied** when the caller has no way to ask the user —
approval is never implicit. How the question gets asked depends on the mode:

- **voice** — Alex asks aloud and listens for yes/no.
- **text** — a prompt on stdin.
- **web** — an approve/deny card appears in the chat; the request waits, and an
  unanswered card times out as a denial.

Two further limits apply regardless of approval:

- `SHELL_DENY_PATTERNS` blocks shell commands that no confirmation should be
  able to authorise (`format`, `diskpart`, `reg delete`, recursive `C:\`
  deletes).
- `ALLOWED_FILE_PATHS` restricts every tool that *modifies* the filesystem to
  your own directories. Reading and listing are unrestricted.

To let plans run dangerous tools unattended, set `AGENT_AUTO_CONFIRM=true`.
It is off by default, deliberately.

---

## Project structure

```
alex/
├── main.py                  # Entry point: voice, text, server, test
├── server.py                # Flask API + confirmation broker
├── config.py                # All settings, read from .env
├── pytest.ini
│
├── core/
│   ├── assistant.py         # Orchestrator: listen → dispatch → think → act → speak
│   ├── brain.py             # LLM providers, fast path, agentic loop, step chaining
│   ├── planner.py           # Plan/Step model, decomposition, dependency graph, reflection
│   ├── tool_registry.py     # @tool decorator, ToolResult, safety gate
│   ├── command_dispatcher.py# Prefix-matched commands that skip the LLM
│   ├── task_manager.py      # Background tasks
│   ├── monitor.py           # CPU/RAM/disk watchers
│   ├── listener.py          # Whisper STT
│   ├── speaker.py           # pyttsx3 TTS
│   └── wake_word.py         # "Hey Alex" detection
│
├── tools/                   # The 34 tools, auto-registered on import
│   ├── web_tools.py    file_tools.py    system_tools.py
│   └── code_tools.py   data_tools.py    notification_tools.py
│
├── memory/
│   ├── long_term.py         # SQLite facts, tasks, conversation log, semantic recall
│   └── context.py           # Active window, time of day, username
│
├── utils/                   # logger, audio_utils, system_info
├── gui/                     # index.html, style.css, app.js
├── scripts/                 # One-off helpers (model discovery)
└── tests/                   # 168 tests
```

---

## Configuration

Everything lives in `.env` — see `.env.example` for the annotated full list.
The settings you're most likely to touch:

| Setting | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini`, `openai`, `openrouter`, or `ollama` |
| `GEMINI_API_KEY` | *(empty)* | Your Google Gemini key |
| `AGENT_MODE` | `true` | Enable multi-step planning |
| `MAX_AGENT_STEPS` | `10` | Step ceiling per plan |
| `MAX_AGENT_ITERATIONS` | `3` | execute → reflect rounds per goal |
| `AGENT_TIMEOUT` | `120` | Seconds before a plan is abandoned |
| `AGENT_AUTO_CONFIRM` | `false` | Let plans run dangerous tools unasked |
| `ENFORCE_FILE_ALLOWLIST` | `true` | Restrict file writes to your folders |
| `CONFIRMATION_TIMEOUT` | `120` | Seconds a web approval card stays valid |
| `WHISPER_MODEL_SIZE` | `base` | `tiny` … `large` |
| `WAKE_WORD` | `hey alex` | Custom wake word |

---

## HTTP API

`python main.py --server` serves the GUI and this API on `127.0.0.1:5000`.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/status` | Assistant identity, provider, boot progress, system stats |
| `GET` | `/api/stats` | CPU, RAM, disk, battery, network, uptime |
| `GET` | `/api/assistant-status` | Subsystem summary: tool count, memory stats, active plan |
| `POST` | `/api/chat` | `{"message": "..."}` → response, action, params, plan |
| `POST` | `/api/action` | `{"action": "web_search", "params": {...}}` → run one tool |
| `GET` | `/api/actions` | All registered tools, grouped by category |
| `GET` | `/api/confirmations` | Approvals waiting on the user |
| `POST` | `/api/confirm` | `{"confirmation_id": "...", "approved": true}` |
| `GET` | `/api/plan` | The plan currently executing, or `{"status": "idle"}` |
| `GET` | `/api/memory` | Stored facts (optional `?category=`) |
| `POST` | `/api/memory` | `{"key": "...", "value": "...", "category": "..."}` |
| `DELETE` | `/api/memory/<key>` | Forget one fact |
| `GET` | `/api/tasks` | Background tasks (`?include_done=true` for finished ones) |
| `DELETE` | `/api/tasks/<id>` | Cancel a background task |
| `GET` | `/api/task-history` | Past agentic tasks (`?limit=`) |

A `/api/chat` or `/api/action` call that reaches a `CONFIRM` tool blocks while
the browser answers it. Poll `/api/confirmations`, then `POST /api/confirm`.

---

## Adding a tool

Drop a function in any module under `tools/` and decorate it. It registers on
import and the LLM sees its description immediately — no prompt editing.

```python
from core.tool_registry import tool, ToolResult, SafetyLevel

@tool(
    name="coffee_brew",
    description="Start the coffee machine",
    parameters={
        "strength": {"type": "string", "description": "mild|strong", "required": False},
    },
    category="home",
    safety=SafetyLevel.CONFIRM,   # omit for SAFE
)
def coffee_brew(params: dict) -> ToolResult:
    strength = params.get("strength", "mild")
    return ToolResult(success=True, message=f"Brewing a {strength} coffee.")
```

If your file is a new module, add it to `tools/__init__.py`.

Return a `ToolResult` (or a plain string / dict, which gets wrapped). Set
`safety=SafetyLevel.CONFIRM` for anything destructive — the registry will then
refuse to run it without an approval channel.

---

## Keyboard shortcuts (web UI)

| Shortcut | Action |
|---|---|
| `Enter` | Send message (`Shift+Enter` for a newline) |
| `Ctrl+L` | Focus chat input |
| `Ctrl+M` | Toggle microphone |
| `Ctrl+K` | Toggle the side panel |
| `Escape` | Return to standby, close the plan drawer |

---

## Tests

```bash
python -m pytest
```

168 tests covering the tool registry and its safety gate, planner routing and
dependency ordering, brain response parsing and step chaining, the file
allow-list, the shell deny-list, the command dispatcher, listen adapters, and
the HTTP API. No network, microphone or API key required.

---

## Roadmap

See [PLAN.md](PLAN.md) for the current improvement plan and what's already
landed.

## License

Personal project.
