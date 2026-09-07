# A.L.E.X — Improvement & Bugfix Roadmap

Status of the codebase as analysed: 9 packages, 34 registered tools, 23 passing tests
(covering only `CommandDispatcher` and the `listen()` adapters). The `ToolRegistry` +
`Planner` architecture is sound; the problems are concentrated in the seams between
subsystems, in paths that were left behind by the `actions/` → `tools/` migration, and
in a safety gate that is bypassed on two of the three execution paths.

Phases are ordered by risk. Phase 0 and 1 are bugs; Phase 2 onward is improvement.

---

## Phase 0 — Safety-critical (do first)

### 0.1 Confirmation gate is bypassed on the web and agentic paths

`ToolRegistry.execute()` treats a missing `confirm_callback` as **approval**:

```python
# core/tool_registry.py:116
if spec.safety == SafetyLevel.CONFIRM:
    if confirm_callback and not confirm_callback(name, params):
        return ToolResult(success=False, ...)
```

Five tools are `CONFIRM`-level: `code_run`, `shell_run`, `file_delete`, `process_kill`,
`system_power`. Three call sites reach them:

| Call site | Passes callback? | Result |
|---|---|---|
| `core/assistant.py:233` (voice fast path) | yes | correct — asks by voice |
| `core/assistant.py:354` (`process_text_full`, used by the web UI) | **no** | executes silently |
| `core/brain.py:401` (agentic step execution) | **no** (`confirm_callback=None`, comment says "auto-confirm safe tools") | executes silently |

So an LLM-generated plan containing `shell_run` or `system_power`, or any web-chat
message, runs destructive tools with no gate. `gui/app.js` has no confirmation UI at
all — its line 457 "awaiting confirmation" string is a canned demo-mode response, not a
real flow.

**Fix — invert the default.** In `ToolRegistry.execute()`, deny when no callback is
supplied:

```python
if spec.safety == SafetyLevel.CONFIRM:
    if confirm_callback is None:
        return ToolResult(success=False,
                          message=f"'{name}' requires confirmation and none was available.",
                          error="No confirmation channel")
    if not confirm_callback(name, params):
        return ToolResult(...)  # as today
```

Then supply a callback everywhere:
- `process_text_full` — thread an explicit `confirm_callback` parameter through; the
  Flask layer supplies one (see 0.2).
- `brain._execute_single_step` — accept a `confirm_callback` on `Brain`, set by
  `Assistant`, and pass it down. Add a config flag `AGENT_AUTO_CONFIRM` (default
  `false`) for users who deliberately want unattended plans.

**Verify:** new tests asserting `execute("shell_run", {...})` with no callback returns
`success=False` and that the tool function was never called (monkeypatch it).

### 0.2 Two-step confirmation for the web UI

The REST API is request/response, so voice-style blocking confirmation does not fit.
Add a pending-confirmation store:

- `POST /api/chat` returns `{"needs_confirmation": true, "confirmation_id": "...",
  "tool": "shell_run", "params": {...}, "response": "<friendly warning>"}` instead of
  executing.
- `POST /api/confirm` with `{"confirmation_id": ..., "approved": true}` executes and
  returns the result.
- Entries expire after ~60 s.
- `gui/app.js`: render an inline approve/deny card in the chat stream for
  `needs_confirmation` responses.

Also fix `/api/action` (`server.py:182`) — it executes **any** tool by name with no
gate, which is a full remote-shell endpoint on `127.0.0.1`. Route it through the same
confirmation store.

### 0.3 Secrets and generated data are unprotected

There is no `.gitignore` and `.env` holds live API keys. The directory is not yet a git
repo, so this is cheap to fix now and expensive later.

Create `.gitignore`:

```
.env
__pycache__/
.pytest_cache/
data/logs/
data/recordings/
data/screenshots/
data/memory.db
*.pyc
```

Confirm `.env.example` lists every key `config.py` reads (currently it is missing
`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `AGENT_MODE`, `MAX_AGENT_STEPS`,
`AGENT_TIMEOUT`, `PARALLEL_STEPS`, `LLM_RETRY_COUNT`, `LLM_RETRY_DELAY`,
`AUDIO_INPUT_DEVICE`).

### 0.4 `shell_run` has no allowlist

`tools/code_tools.py:93` passes arbitrary strings to PowerShell. `file_tools.py` has
`_is_allowed_path()` guarding the filesystem, but `shell_run` can trivially step around
it (`Remove-Item C:\...`). At minimum: log every invocation at WARNING (already done),
require confirmation (0.1 handles this), and add a configurable
`SHELL_DENY_PATTERNS` list in `config.py` (e.g. `format`, `del /f /s /q`,
`Remove-Item -Recurse -Force C:\`, `diskpart`, `reg delete`) checked before execution.

---

## Phase 1 — Correctness bugs

### 1.1 Dead `assistant.router` references crash the fallback paths

`server.py:197` and `server.py:212` call `assistant.router.execute(...)` /
`assistant.router.get_available_actions()`. `Assistant` has had no `router` attribute
since the `actions/` → `tools/` migration, so these `AttributeError` instead of
degrading gracefully. Delete both fallback branches — `_tool_registry` is always the
path now.

### 1.2 Plan results are never fed back into the plan

`brain._execute_plan()` builds `step_results: dict[int, str]` and then never uses it.
`Planner.create_plan()` accepts a `previous_results` argument that only the initial call
passes (as `"None"`). Consequences:

- A step cannot consume a previous step's output. `depends_on` only sequences
  execution; the dependent step's `params` are frozen at plan-creation time.
- `Planner.reflect()` returns `additional_steps`, which `_think_agentic` discards
  (`core/brain.py:315`) — the ReAct loop never actually iterates.

The docstring at `core/brain.py:276` ("Feed results back to LLM after each step")
describes behaviour that does not exist.

**Fix:**
1. Add placeholder substitution in `_execute_single_step`: before executing, walk
   `step.params` and replace `{{step_1.result}}`-style tokens from `step_results`.
   Document the syntax in `PLAN_PROMPT_TEMPLATE` so the LLM emits it.
2. After `reflect()`, if `goal_accomplished` is false and `additional_steps` is
   non-empty, append them and re-run `_execute_plan` — bounded by `MAX_AGENT_STEPS`
   total and the existing `AGENT_TIMEOUT`.

### 1.3 Special commands break the web UI

`Assistant._handle_special_commands()` speaks via TTS and returns `True`;
`process_text_full` then returns the literal string `"Special command handled."`
(`core/assistant.py:342`). So a web user typing "status" hears the answer from the
server's speakers and sees a placeholder in the chat.

**Fix:** have `_handle_special_commands` return `str | None` (the response text) rather
than `bool`, let the caller decide whether to speak it or return it. The voice loop
speaks it; `process_text_full` returns it.

### 1.4 "bye" from the web UI half-kills the server

The same handler calls `self.shutdown()` for `quit`/`exit`/`bye`, which cancels all
background tasks, closes the memory DB, and calls `sys.exit(0)` — inside a Flask worker
thread. The process survives but the singleton `Assistant` is left with a closed SQLite
connection, so every later request fails.

**Fix:** gate the shutdown branch on the interaction mode. In server mode treat
"goodbye" as a plain conversational response.

### 1.5 Stale plan state leaks

`Brain._current_plan` is only ever assigned (`core/brain.py:304`) and never cleared, so
`get_current_plan()` and `GET /api/plan` keep returning the last agentic plan
indefinitely — the GUI shows a completed plan as if it were live. Clear it at the start
of `think()` and set `status` correctly on completion. `self._plan_lock` is declared and
never used.

### 1.6 The shared `Assistant` is not thread-safe

`server.py` keeps one global `_assistant`, and every `/api/chat` spawns a thread
(`server.py:153`). Concurrent requests share `Brain._chat` (the Gemini chat session),
`conversation_history`, and `_current_plan`. Two overlapping requests interleave
history and corrupt each other's context.

**Fix:** serialise `Brain.think()` with a lock (simplest, correct for a single-user
assistant), and note the constraint in the code. `PARALLEL_STEPS` inside one plan is
fine — those go to different tools.

### 1.7 `_should_use_agent` heuristic misroutes

`Planner.should_plan()` (`core/planner.py:202`) sends anything over 25 words to the
planner, including plain conversation. Its exclusion list is a hand-maintained set of
phrases. Cheap improvement: also skip planning when the input contains no verb from the
tool vocabulary, and require `indicator_count >= 2` *and* a tool-ish verb. Add unit
tests pinning the routing decision for ~20 representative inputs — this is pure
function, easy to test, and currently untested.

---

## Phase 2 — Architecture decisions

### 2.1 Resolve plugins vs tools (pick one)

`plugins/` contains `PluginBase`, a loader, and four plugins. Nothing loads them except
`GET /api/plugins`, which constructs a throwaway `PluginLoader`. Their functionality is
already reimplemented as first-class tools: `weather_get`, `reminder_set`, `email_send`,
`code_run`. The README's "Adding Custom Plugins" section documents a mechanism that has
no effect.

Two coherent options:

- **(A) Delete `plugins/`** and the `/api/plugins` endpoint. Tools are the extension
  point; `@tool` is a better API than `PluginBase`. Least code, recommended.
- **(B) Bridge them:** have `PluginLoader.discover()` wrap each plugin action in a
  `ToolSpec` and register it, then call it from `Assistant._init_tool_registry()`. Keeps
  a drop-in-a-file extension story for non-tool authors.

Either way the README must match. Decide before writing docs (Phase 4).

### 2.2 Retire the duplicate memory layer

`memory/storage.py` + `memory/conversation.py` are only referenced by each other;
`Assistant` uses `memory/long_term.py`. Confirm with a fresh grep, then delete the pair,
or fold anything still wanted (`search_conversations`) into `LongTermMemory`.

### 2.3 Retire `config.SYSTEM_PROMPT`

The 58-line hardcoded action list at `config.py:149` is used only when the registry
fails to load (`core/brain.py:125`), and it names actions that no longer exist
(`open_app`, `file_operation`, …) — they only resolve through
`ToolRegistry._find_by_alias`. A fallback that emits invalid tool names is worse than no
fallback: if the registry is empty, say so and refuse to act. Delete the constant and
the alias map once nothing emits the old names.

### 2.4 Scratch scripts in the root

`check_models.py`, `find_model.py`, `test_api.py`, `test_brain.py`, `test_chat.py` are
one-off scripts sitting beside the entry points; the last three are named like tests but
are not collected by `pytest` from `tests/`. Move the useful ones to `scripts/`, delete
the rest.

---

## Phase 3 — Test coverage

Current: 23 tests over `CommandDispatcher` and `listen()`. Everything load-bearing is
untested. Target order:

1. **`tests/test_tool_registry.py`** — registration, alias resolution, result
   normalisation (str/dict/ToolResult/None), exception → `ToolResult(success=False)`,
   and the Phase 0.1 confirmation semantics.
2. **`tests/test_planner.py`** — `should_plan()` routing table; `_parse_json_response`
   against messy LLM output (fenced, prose-wrapped, trailing commas); `get_ready_steps`
   dependency ordering; cyclic/missing `depends_on` handling.
3. **`tests/test_brain_parse.py`** — `_parse_response` with: no action block, malformed
   JSON, multiple blocks, action block with prose around it.
4. **`tests/test_server_api.py`** — Flask test client with a mocked `Assistant`, over
   every endpoint including the new confirmation flow.
5. **`tests/test_file_tools.py`** — `_is_allowed_path` against traversal
   (`~/Desktop/../../Windows`), symlinks, and UNC paths.

Add `pytest.ini` fixing `testpaths = tests` so the root scratch scripts are never
collected.

---

## Phase 4 — Documentation & hygiene

### 4.1 Rewrite `README.md`

It documents an architecture that no longer exists: an `actions/` directory and
`core/action_router.py`, neither of which is present. Missing entirely: `planner.py`,
`task_manager.py`, `monitor.py`, `command_dispatcher.py`, `long_term.py`, the `tools/`
package, the `openrouter` provider, `AGENT_MODE` and the agentic pipeline, and the
memory/tasks/plan REST endpoints.

Rewrite around the real pipeline:
`listen → special commands → dispatcher → Brain (fast | agentic) → ToolRegistry → speak`,
with the 34 tools grouped by category and a short "adding a tool with `@tool`" section
replacing the plugin section (per 2.1).

### 4.2 Document the API

One table of the 14 endpoints with request/response shapes — the GUI is the only
current spec.

### 4.3 Initialise git

After `.gitignore` lands (0.3), `git init` and commit. Every fix above becomes
reviewable and revertible; right now there is no undo.

---

## Phase 5 — Improvements worth doing after the above

- **Streaming responses.** `/api/chat` blocks up to 60 s (`server.py:155`) and returns
  one blob. Server-sent events would let the GUI show plan steps as they execute — the
  `_notify_plan` listener hooks in `Brain` already exist and have no consumer.
- **Tool-call API instead of fenced JSON.** `ToolRegistry.get_json_schema()` is written
  and unused. Gemini and OpenAI both support native function calling, which removes the
  regex parsing in `_parse_response` and its whole class of failures.
- **Structured errors to the user.** `ToolResult.to_response()` returns raw
  `f"Error: {e}"` strings that get spoken aloud, contradicting the system prompt's "never
  say technical jargon" rule. Map failures to friendly sentences.
- **Wake-word accuracy.** `WAKE_WORD_ENGINE` supports `porcupine`, but only the
  Whisper path looks implemented — verify and either finish or remove the option.
- **`data/logs/` growth.** No rotation; `utils/logger.py` writes one file per day
  forever. Add retention.

---

## Suggested execution order

| Step | Work | Rough size |
|---|---|---|
| 1 | 0.3 `.gitignore` + `.env.example`, 4.3 `git init`, commit baseline | 15 min |
| 2 | 0.1 confirmation default + tests | half day |
| 3 | 1.1, 1.3, 1.4, 1.5 — small independent bug fixes | half day |
| 4 | 0.2 web confirmation flow (server + GUI) | 1 day |
| 5 | 1.6 thread safety, 0.4 shell deny-list | half day |
| 6 | 2.1 plugins decision, 2.2/2.3/2.4 deletions | half day |
| 7 | Phase 3 tests | 1–2 days |
| 8 | 1.2 plan result passing (the largest functional change) | 1 day |
| 9 | 4.1/4.2 docs rewrite, once the code is stable | half day |

Steps 1–3 are independent and can land in any order. Step 9 must come last — writing
docs before 2.1 is decided means writing them twice.
