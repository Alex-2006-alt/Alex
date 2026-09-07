# A.L.E.X — Improvement Roadmap

> New capabilities (YouTube, power, startup greeting, WhatsApp, phone calls)
> are planned separately in [FEATURES.md](FEATURES.md). This file covers the
> health of what already exists.

Phases 0–4 of the original roadmap are complete. What follows records what
landed and why, then lists the work that is still open.

Test coverage went from 23 tests (dispatcher and listen adapters only) to 168.

---

## Done

### Phase 0 — Safety

**Confirmation gate inverted.** `ToolRegistry.execute()` treated a missing
`confirm_callback` as approval. Two of the three call sites passed none —
`Assistant.process_text_full` (the web path) and `Brain._execute_single_step`
(every agentic plan step) — so `shell_run`, `system_power`, `file_delete`,
`process_kill` and `code_run` ran with no gate. `/api/action` executed any tool
by name with no gate at all.

A `CONFIRM` tool is now denied when no confirmation channel exists.
Unattended execution requires passing `ToolRegistry.AUTO_APPROVE` explicitly,
which only `AGENT_AUTO_CONFIRM=true` does.

**Web confirmation flow.** HTTP can't ask mid-request, so a request that hits a
`CONFIRM` tool parks a pending confirmation and blocks on it. The browser polls
`GET /api/confirmations`, shows an approve/deny card, and answers via
`POST /api/confirm`. Chat requests stay open while a card is unanswered; a
timeout is a denial.

**Shell deny-list.** `SHELL_DENY_PATTERNS` blocks commands confirmation should
not be able to authorise — `format`, `diskpart`, `reg delete`, recursive `C:\`
deletes — checked on whitespace-normalised, case-folded input.

**File allow-list enforced.** `_is_allowed_path` was defined but never called
from any tool, so `ALLOWED_FILE_PATHS` restricted nothing. Every mutating tool
(`file_write`, `file_move`, `file_copy`, `file_delete`, `file_mkdir`) now checks
it. Reading and listing stay unrestricted; `ENFORCE_FILE_ALLOWLIST` switches it
off.

**Secrets.** `.gitignore` added (excludes `.env`, `data/`, caches) before
`git init`, and `.env.example` now lists every variable `config.py` reads.

### Phase 1 — Correctness

- **Dead `assistant.router` fallbacks** in `/api/action` and `/api/actions`
  removed. The attribute has not existed since the `actions/` → `tools/`
  migration, so they raised `AttributeError` instead of degrading.
- **The ReAct loop now loops.** `step_results` was collected and never read, and
  `reflect()`'s `additional_steps` was discarded. Steps can now consume earlier
  output via `{{step_N.result}}` (nested dicts and lists included; an unknown
  reference is left visible rather than blanked), and `_think_agentic` iterates
  execute → reflect up to `MAX_AGENT_ITERATIONS`, capped at `MAX_AGENT_STEPS`.
  `AGENT_TIMEOUT` is measured from plan creation so it covers every iteration.
- **Special commands** return their text instead of speaking it, so web users
  read the answer rather than hearing it from the server's speakers.
- **"bye" over HTTP** no longer calls `shutdown()`, which closed the memory DB
  that later requests needed.
- **Stale plan state** cleared at the start of each `think()`, under the lock
  that was declared but unused. `/api/plan` was serving finished plans as live.
- **Request serialisation.** `Assistant.process_text_full` holds a lock, since
  Brain's chat session, history and current plan are shared mutable state and
  every `/api/chat` runs on its own thread.

### Phase 2 — Architecture

- **`plugins/` deleted.** Nothing loaded it but `GET /api/plugins`, and all four
  plugins were already reimplemented as tools. `@tool` is the single extension
  point.
- **`memory/storage.py` and `memory/conversation.py` deleted.** They referenced
  only each other; their one unique capability is now
  `LongTermMemory.search_conversation()`.
- **`memory/context.py` wired up.** It was written but never called, despite the
  README and system prompt both promising context awareness. Active window, time
  of day and username now reach both the fast and agentic paths.
- **`config.SYSTEM_PROMPT` deprecated** to `_LEGACY_SYSTEM_PROMPT`. It was only
  used when the registry failed to load and advertised action names that no
  longer exist. Both it and `Planner._get_tool_descriptions` now say plainly
  that nothing is callable instead of handing the LLM invalid names.
- **Root scripts sorted.** `check_models.py` and `find_model.py` moved to
  `scripts/`; `test_api.py`, `test_brain.py`, `test_chat.py` deleted — their
  endpoint coverage is now in `tests/test_server_api.py`, which needs no running
  server. `pytest.ini` pins `testpaths` to `tests/`.

### Phase 3 — Tests

`tests/test_tool_registry.py`, `test_planner.py`, `test_brain.py`,
`test_file_tools.py`, `test_shell_safety.py`, `test_server_api.py`,
`test_server_confirmations.py`. No network, microphone or API key required.

### Phase 4 — Docs

README rewritten against the real architecture, with the request-flow diagram,
all 34 tools by category, the safety model, and the full HTTP API table.

---

## Still open

### 1. Native function calling
`ToolRegistry.get_json_schema()` is written and unused. Gemini and OpenAI both
support function calling, which would delete the ```` ```action ```` regex in
`Brain._parse_response` and its whole class of parse failures. The registry
already produces the schema; the work is per-provider request/response wiring
and a fallback for Ollama models that lack it.

### 2. Streaming responses
`/api/chat` blocks up to 60 s and returns one blob, so a five-step plan shows
nothing until it finishes. `Brain._notify_plan` already emits `plan_started`,
`step_started`, `step_done` and `plan_done` events and has no consumer —
server-sent events would let the GUI render steps as they execute.

### 3. Friendlier tool errors
`ToolResult.to_response()` returns raw `f"Error: {e}"` strings that get spoken
aloud, contradicting the system prompt's "never say technical jargon" rule. Map
common failures (file not found, network down, permission denied) to sentences.

### 4. Planner routing heuristic
`should_plan()` still routes on a hand-maintained phrase list plus a 25-word
threshold. `tests/test_planner.py` pins the current behaviour, so it can now be
replaced safely — the obvious next step is requiring a tool-ish verb alongside
the complexity indicators.

### 5. Wake-word engine
`WAKE_WORD_ENGINE` accepts `porcupine`, but only the Whisper path appears
implemented. Verify, then either finish it or drop the option.

### 6. Log rotation
`utils/logger.py` writes one file per day under `data/logs/` forever. Add
retention.

### 7. Concurrency ceiling
The request lock makes the shared `Assistant` correct for one user at a time,
which is what it is for. Real concurrency would need per-session Brain
instances.
