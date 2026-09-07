"""
ALEX — AI Brain (Upgraded)
LLM integration with ReAct-style agentic planning loop.
Supports single-step (fast) and multi-step (agentic) modes.
Integrates long-term memory and dynamic tool registry.
"""

import json
import re
import time
import threading
from typing import Any, Callable

from utils.logger import log
import config


class Brain:
    """
    The upgraded AI brain of ALEX.

    Modes:
    1. Fast mode (AGENT_MODE=False or simple request): single LLM call → one action
    2. Agentic mode (complex request): Plan → Execute steps → Reflect → Final response

    Integrations:
    - ToolRegistry: dynamic tools the LLM can use
    - LongTermMemory: remembers facts across sessions
    - Planner: decomposes complex goals into steps
    """

    def __init__(self, provider: str | None = None):
        self.provider = provider or config.LLM_PROVIDER
        self.conversation_history: list[dict] = []
        self._client = None
        self._chat = None

        # Optional integrations (lazy-loaded)
        self._tool_registry = None
        self._memory = None
        self._planner = None
        self._task_manager = None
        self._context = None
        self._confirm_callback: Callable | None = None

        # Plan execution state
        self._current_plan = None
        self._plan_lock = threading.Lock()
        self._plan_listeners: list[Callable] = []

        log.info(f"🧠 Brain initialized | provider={self.provider} | agent_mode={config.AGENT_MODE}")

    # ─── INTEGRATIONS ────────────────────────────────────────────────────────

    def set_tool_registry(self, registry):
        self._tool_registry = registry

    def set_memory(self, memory):
        self._memory = memory

    def set_task_manager(self, task_manager):
        self._task_manager = task_manager

    def set_confirm_callback(self, callback: Callable | None):
        """
        Set the channel used to confirm CONFIRM-level tools during plan execution.
        Signature: ``fn(tool_name: str, params: dict) -> bool``.
        """
        self._confirm_callback = callback

    def _step_confirm_callback(self) -> Callable | None:
        """
        Resolve the confirmation channel for an agentic step.

        Without one, CONFIRM-level tools are denied by ToolRegistry — which is
        the safe outcome. AGENT_AUTO_CONFIRM is the explicit opt-out.
        """
        if self._confirm_callback is not None:
            return self._confirm_callback
        if config.AGENT_AUTO_CONFIRM:
            from core.tool_registry import ToolRegistry
            log.warning("⚠️ AGENT_AUTO_CONFIRM is on — plan steps run dangerous tools unattended")
            return ToolRegistry.AUTO_APPROVE
        return None

    def add_plan_listener(self, callback: Callable):
        self._plan_listeners.append(callback)

    def _notify_plan(self, event: str, data: dict):
        for cb in self._plan_listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    # ─── CLIENT INIT ─────────────────────────────────────────────────────────

    def _init_client(self):
        if self._client is not None:
            return
        if self.provider == "gemini":
            self._init_gemini()
        elif self.provider == "ollama":
            self._init_ollama()
        elif self.provider == "openai":
            self._init_openai()
        elif self.provider == "openrouter":
            self._init_openrouter()
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    def _build_system_prompt(self) -> str:
        """Build a dynamic system prompt including live tool descriptions."""
        base = f"""You are {config.ASSISTANT_NAME}, a friendly, warm, witty, and supportive AI companion and personal assistant on Windows.

PERSONALITY & VOICE TONE:
- Talk like a close, smart friend — casual, supportive, cheerful, and helpful.
- Keep responses natural, human-like, and conversational.
- CRITICAL: Never say raw URLs or technical jargon out loud (e.g. NEVER say "opening url https://www.youtube.com").
- Instead, refer naturally to what the user requested, e.g.:
  - User: "open youtube" → Alex: "Sure thing! Opening YouTube for you."
  - User: "open chrome" → Alex: "Got it, popping open Chrome!"
  - User: "what's the weather" → Alex: "Let me check the weather for you!"
  - User: "search for python" → Alex: "On it! Looking that up right now."

RESPONSE FORMAT:
For simple requests (conversation or single action), respond normally:
  Friendly conversational text...
  ```action
  {{"action": "tool_name", "params": {{"key": "value"}}}}
  ```

For complex multi-step tasks, handle planning automatically.
If no action is needed, respond without an action block.

RULES:
1. Always sound like a friendly companion, never like a robotic system log.
2. Keep spoken responses concise, warm, and natural.
3. For destructive actions (delete, shutdown), warn and confirm thoughtfully.
4. NEVER respond with an empty message. Always say SOMETHING friendly.
5. Do NOT include raw function names or http links in your conversational speech.
6. If the user tells you personal details (likes, dislikes, info), use the `memory_store` tool to remember it for future chats.
"""

        # Inject live tool descriptions. Without a registry there is nothing
        # the LLM could usefully call, so say so rather than advertising the
        # old hardcoded action names that no longer resolve to anything.
        if self._tool_registry and len(self._tool_registry):
            tool_section = self._tool_registry.get_descriptions_for_prompt()
            base += f"\n\nAVAILABLE TOOLS:\n{tool_section}\n"
        else:
            log.error("No tools registered — the LLM will be told it cannot act")
            base += (
                "\n\nAVAILABLE TOOLS: none. Your tool registry failed to load, so you "
                "cannot control the PC right now. Tell the user that plainly if they "
                "ask for an action, and never emit an action block.\n"
            )

        return base

    def _init_gemini(self):
        try:
            import google.generativeai as genai

            if not config.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not set in .env")

            genai.configure(api_key=config.GEMINI_API_KEY)
            system_prompt = self._build_system_prompt()
            self._client = genai.GenerativeModel(
                model_name=config.GEMINI_MODEL,
                system_instruction=system_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=config.LLM_TEMPERATURE,
                    max_output_tokens=config.LLM_MAX_TOKENS,
                ),
            )
            self._chat = self._client.start_chat(history=[])
            log.info(f"✅ Gemini initialized ({config.GEMINI_MODEL})")
        except Exception as e:
            log.error(f"Gemini init failed: {e}")
            raise

    def _init_ollama(self):
        try:
            import ollama
            ollama.list()
            self._client = ollama
            log.info(f"✅ Ollama initialized ({config.OLLAMA_MODEL})")
        except Exception as e:
            log.error(f"Ollama init failed: {e}")
            raise

    def _init_openai(self):
        try:
            from openai import OpenAI
            if not config.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not set in .env")
            self._client = OpenAI(api_key=config.OPENAI_API_KEY)
            log.info(f"✅ OpenAI initialized ({config.OPENAI_MODEL})")
        except Exception as e:
            log.error(f"OpenAI init failed: {e}")
            raise

    def _init_openrouter(self):
        """OpenRouter: OpenAI-compatible API supporting 200+ models (many free)."""
        try:
            from openai import OpenAI
            if not config.OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY not set in .env")
            self._client = OpenAI(
                api_key=config.OPENROUTER_API_KEY,
                base_url=config.OPENROUTER_BASE_URL,
                default_headers={
                    "HTTP-Referer": "https://github.com/alex-assistant",
                    "X-Title": "ALEX Personal Assistant",
                },
            )
            log.info(f"✅ OpenRouter initialized ({config.OPENROUTER_MODEL})")
        except Exception as e:
            log.error(f"OpenRouter init failed: {e}")
            raise

    # ─── MAIN THINK METHOD ───────────────────────────────────────────────────

    def think(self, user_input: str) -> dict:
        """
        Process user input and return a structured response.

        In AGENT_MODE, complex requests trigger multi-step planning.
        Simple requests use the fast single-step path.

        Returns:
            dict with: response, action, params, plan (optional)
        """
        self._init_client()

        log.info(f"🤔 Think: \"{user_input[:80]}\"")

        # Drop the previous plan: /api/plan and get_current_plan() would
        # otherwise keep serving a finished plan as if it were still running.
        with self._plan_lock:
            self._current_plan = None

        # Extract facts from user input into long-term memory
        if self._memory:
            self._memory.extract_facts_from_text(user_input)
            self._memory.log_conversation("user", user_input)

        # Decide: fast path or agentic path
        if config.AGENT_MODE and self._should_use_agent(user_input):
            result = self._think_agentic(user_input)
        else:
            result = self._think_fast(user_input)

        # Log assistant response to memory
        if self._memory and result.get("response"):
            self._memory.log_conversation("assistant", result["response"])

        # Store in conversation history
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": result.get("response", "")})

        max_messages = config.CONTEXT_WINDOW_SIZE * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

        log.info(f"💡 Response: \"{str(result.get('response', ''))[:80]}\"")
        return result

    def _should_use_agent(self, user_input: str) -> bool:
        """Decide if input needs the agentic planner or fast path."""
        if self._planner is None:
            self._init_planner()
        return self._planner.should_plan(user_input)

    def _init_planner(self):
        """Lazy-initialize the planner."""
        from core.planner import Planner
        self._planner = Planner(
            llm_caller=self._raw_llm_call,
            tool_registry=self._tool_registry,
        )
        for cb in self._plan_listeners:
            self._planner.add_plan_listener(cb)

    # ─── FAST PATH ───────────────────────────────────────────────────────────

    def _think_fast(self, user_input: str) -> dict:
        """Single LLM call → parse action → return. Fast, simple path."""
        # Build prompt with memory context
        enriched_input = self._enrich_with_memory(user_input)

        try:
            raw = self._raw_llm_call_with_history(enriched_input)
            result = self._parse_response(raw)

            # Guard against empty responses — the #1 cause of "Alex not responding"
            if not result.get("response") or not result["response"].strip():
                log.warning("LLM returned an empty response after parsing")
                result["response"] = "I'm sorry, I couldn't process that properly. Could you try rephrasing?"

            # Guard against Alex claiming to have done something it didn't.
            # Under load the model often returns "Opening YouTube for you!" with
            # no action block at all, which reads as a silent failure.
            result = self._repair_unfulfilled_promise(user_input, enriched_input, result)

            log.info(f"⚡ Fast path: action={result.get('action')}")
            return result
        except Exception as e:
            log.error(f"Fast think error: {e}")
            return {"response": f"Sorry, I had trouble with that. ({str(e)[:100]})", "action": None, "params": None}

    # Phrases that promise an action is under way. If one of these shows up
    # with no action block, Alex is about to claim it did something it didn't.
    _PROMISE_RE = re.compile(
        r"\b(opening|open(?:s|ed)? up|launching|playing|putting on|starting|"
        r"firing up|pulling up|popping open|searching for|looking that up|"
        r"taking a screenshot|shutting down|sending)\b",
        re.IGNORECASE,
    )

    # Question forms, and phrasings that describe capabilities rather than
    # announce an action. "What can you do" legitimately answers with
    # "...opening apps, playing music..." and must not be treated as a promise.
    _QUESTION_STARTS = (
        "what", "who", "when", "where", "why", "how", "which",
        "can you", "could you", "do you", "are you", "is there",
        "tell me", "explain", "describe", "list",
    )
    _CAPABILITY_HINTS = (
        "i can ", "i can'", "i'm able", "i am able", "such as", "for example",
        "here's what", "here is what", "things like", "like this:", "•", "- ",
        "1.", "2.", "my abilities", "i'm capable", "i am capable",
    )
    # An action acknowledgement is a short one-liner. A paragraph is prose.
    _MAX_PROMISE_LEN = 240

    def _is_question(self, text: str) -> bool:
        stripped = text.strip().lower()
        return stripped.endswith("?") or stripped.startswith(self._QUESTION_STARTS)

    def _repair_unfulfilled_promise(self, user_input: str, prompt: str, result: dict) -> dict:
        """
        Catch responses that promise an action but carry no action block.

        Retries once with an explicit instruction to emit the block. If the
        model still won't, rewrite the response so Alex admits it rather than
        cheerfully reporting success it never achieved.

        Deliberately conservative: a false positive here destroys a perfectly
        good conversational answer, which is worse than the bug it fixes.
        """
        if result.get("action"):
            return result

        response = result.get("response", "")

        # The user asked a question — an answer is the correct outcome.
        if self._is_question(user_input):
            return result

        # Long or list-shaped replies are describing capabilities, not acting.
        if len(response) > self._MAX_PROMISE_LEN:
            return result

        lowered = response.lower()
        if any(hint in lowered for hint in self._CAPABILITY_HINTS):
            return result

        if not self._PROMISE_RE.search(response):
            return result

        log.warning(f"⚠️ Response promises an action but none was parsed: \"{response[:70]}\"")

        nudge = (
            f"{prompt}\n\n"
            "IMPORTANT: your previous reply said you were performing an action but "
            "contained no ```action``` block, so nothing happened. Reply again and "
            "include the ```action``` block with the correct tool name and params. "
            "If no tool applies, say so plainly instead of implying you acted."
        )

        try:
            retry = self._parse_response(self._raw_llm_call_with_history(nudge))
            if retry.get("action"):
                log.info(f"✅ Recovered missing action on retry: {retry['action']}")
                return retry
        except Exception as e:
            log.warning(f"Action-repair retry failed: {e}")

        log.warning("Could not recover an action — telling the user honestly")
        result["response"] = (
            "Sorry — I said I'd do that but I couldn't actually carry it out. "
            "My AI backend didn't give me a usable command. Could you try again?"
        )
        return result

    # ─── AGENTIC PATH ────────────────────────────────────────────────────────

    def _think_agentic(self, user_input: str) -> dict:
        """
        ReAct-style agentic loop:
        1. Create a plan (LLM decomposes goal into steps)
        2. Execute steps one by one (with tool calls)
        3. Feed results back to LLM after each step
        4. Reflect on final outcome and form response
        """
        log.info(f"🗺️ Agentic mode for: {user_input[:60]}")

        if self._planner is None:
            self._init_planner()

        # Memory + PC context for planning
        context_blocks = []
        try:
            context_blocks.append(self._get_context().get_context_string())
        except Exception:
            pass
        if self._memory:
            mem = self._memory.get_memory_prompt(user_input)
            if mem:
                context_blocks.append(mem)
        memory_context = "\n".join(context_blocks)

        # Step 1: Create plan
        plan = self._planner.create_plan(
            goal=user_input,
            context=memory_context,
        )

        if not plan or not plan.steps:
            # Planner says no multi-step needed, fall back to fast path
            log.info("Planner: no steps needed, using fast path")
            return self._think_fast(user_input)

        plan.status = "running"
        with self._plan_lock:
            self._current_plan = plan
        self._notify_plan("plan_started", plan.to_dict())

        # Steps 2-3: Execute, reflect, and iterate while the goal is unmet.
        # Results accumulate across iterations so late steps can still refer
        # back to early ones.
        step_results: dict[int, str] = {}
        reflection: dict = {}

        for iteration in range(1, max(1, config.MAX_AGENT_ITERATIONS) + 1):
            try:
                self._execute_plan(plan, step_results)
            except Exception as e:
                log.error(f"Plan execution error: {e}")
                plan.status = "failed"
                break

            reflection = self._planner.reflect(plan)

            if reflection.get("goal_accomplished"):
                log.info(f"🎯 Goal accomplished after {iteration} iteration(s)")
                break

            extra = reflection.get("additional_steps") or []
            if not extra:
                break
            if iteration >= config.MAX_AGENT_ITERATIONS:
                log.warning(f"Reflection wanted {len(extra)} more step(s) but the iteration budget is spent")
                break

            added = self._append_steps(plan, extra)
            if not added:
                break
            log.info(f"🔁 Reflection added {added} step(s); running iteration {iteration + 1}")

        final_response = reflection.get("final_response") or f"Task completed! {plan.summary()}"

        plan.status = "done" if not plan.has_failures() else "partial"
        plan.final_response = final_response
        self._notify_plan("plan_done", plan.to_dict())

        # Save to memory
        if self._memory:
            self._memory.save_task(
                goal=user_input,
                status=plan.status,
                steps=[s.to_dict() for s in plan.steps],
                result=final_response,
            )

        return {
            "response": final_response,
            "action": None,
            "params": None,
            "plan": plan.to_dict(),
        }

    def _append_steps(self, plan, steps_data: list[dict]) -> int:
        """
        Append reflection-suggested steps to a running plan.

        Returns the number actually added — the plan's total is capped at
        MAX_AGENT_STEPS so a reflection loop cannot grow it without bound.
        """
        from core.planner import Step

        room = config.MAX_AGENT_STEPS - len(plan.steps)
        if room <= 0:
            log.warning(f"Plan already at MAX_AGENT_STEPS ({config.MAX_AGENT_STEPS}); refusing more")
            return 0

        next_id = max((s.id for s in plan.steps), default=0) + 1
        added = 0
        for s in steps_data[:room]:
            if not s.get("action"):
                continue
            plan.steps.append(Step(
                id=s.get("id") or next_id,
                action=s["action"],
                params=s.get("params", {}) or {},
                description=s.get("description", ""),
                depends_on=s.get("depends_on", []) or [],
            ))
            next_id = max(next_id, plan.steps[-1].id) + 1
            added += 1
        return added

    def _execute_plan(self, plan, step_results: dict[int, str] | None = None):
        """Execute all pending steps in the plan, feeding results forward."""
        from core.planner import StepStatus

        if step_results is None:
            step_results = {}

        # Measured from plan creation, so the budget covers every reflection
        # iteration rather than resetting for each one.
        start_time = plan.created_at

        while not plan.is_done():
            # Check timeout
            if time.time() - start_time > config.AGENT_TIMEOUT:
                log.warning(f"⏰ Plan timed out after {config.AGENT_TIMEOUT}s")
                for step in plan.steps:
                    if step.status == StepStatus.PENDING:
                        step.status = StepStatus.SKIPPED
                break

            # Get steps ready to execute (dependencies met)
            ready_steps = plan.get_ready_steps()
            if not ready_steps:
                # Check if we're stuck
                pending = [s for s in plan.steps if s.status == StepStatus.PENDING]
                if pending:
                    log.warning(f"Plan stuck: {len(pending)} pending steps but none are ready")
                    for s in pending:
                        s.status = StepStatus.SKIPPED
                break

            # Execute ready steps (parallel if config allows)
            if config.PARALLEL_STEPS and len(ready_steps) > 1:
                self._execute_steps_parallel(ready_steps, plan, step_results)
            else:
                for step in ready_steps:
                    self._execute_single_step(step, plan, step_results)

    def _execute_steps_parallel(self, steps, plan, step_results: dict):
        """Execute multiple independent steps in parallel threads."""
        threads = []
        for step in steps:
            t = threading.Thread(
                target=self._execute_single_step,
                args=(step, plan, step_results),
                daemon=True,
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=60)

    # Matches {{step_3.result}} and the shorthand {{step_3}}
    _STEP_REF = re.compile(r"\{\{\s*step[_ ]?(\d+)(?:\.result)?\s*\}\}", re.IGNORECASE)

    def _resolve_params(self, value, step_results: dict[int, str]):
        """
        Replace {{step_N.result}} references with the output of step N.

        Walks nested dicts and lists. An unknown step id is left as-is rather
        than blanked, so a broken reference is visible in the logs and in the
        error the tool returns instead of silently becoming an empty string.
        """
        if isinstance(value, dict):
            return {k: self._resolve_params(v, step_results) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_params(v, step_results) for v in value]
        if not isinstance(value, str):
            return value

        def substitute(match):
            step_id = int(match.group(1))
            if step_id in step_results:
                return str(step_results[step_id])
            log.warning(f"Unresolved plan reference {match.group(0)} — step {step_id} has no result")
            return match.group(0)

        return self._STEP_REF.sub(substitute, value)

    def _execute_single_step(self, step, plan, step_results: dict):
        """Execute a single plan step via the tool registry."""
        from core.planner import StepStatus

        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        self._notify_plan("step_started", {"plan_goal": plan.goal, "step": step.to_dict()})

        log.info(f"▶️ Step {step.id}: {step.action} | {step.description}")

        try:
            if self._tool_registry:
                resolved_params = self._resolve_params(step.params, step_results)
                if resolved_params != step.params:
                    log.info(f"🔗 Step {step.id} params resolved from previous results")
                result = self._tool_registry.execute(
                    step.action,
                    resolved_params,
                    confirm_callback=self._step_confirm_callback(),
                )
                step.result = result.to_response() if hasattr(result, 'to_response') else str(result)
                step.status = StepStatus.DONE if (not hasattr(result, 'success') or result.success) else StepStatus.FAILED
                if hasattr(result, 'success') and not result.success:
                    step.error = result.error
            else:
                step.result = "Error: ToolRegistry is not initialized."
                step.status = StepStatus.FAILED
                step.error = step.result

            # Stored in full: a later step may need the whole output (a file's
            # contents, a scrape). The prompt and UI truncate at their own edges.
            step_results[step.id] = str(step.result)
            log.info(f"✅ Step {step.id} done: {str(step.result)[:100]}")

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step_results[step.id] = f"ERROR: {e}"
            log.error(f"❌ Step {step.id} failed: {e}")

        finally:
            step.finished_at = time.time()
            self._notify_plan("step_done", {"step": step.to_dict()})

    # ─── LLM CALLS ───────────────────────────────────────────────────────────

    def _raw_llm_call(self, prompt: str) -> str:
        """Send a raw prompt to the LLM (no history, no context injection). Retries on empty/failed responses."""
        self._init_client()

        for attempt in range(config.LLM_RETRY_COUNT + 1):
            try:
                raw = self._raw_llm_call_single(prompt)
                if raw and raw.strip():
                    return raw
                log.warning(f"LLM returned empty on raw call (attempt {attempt + 1}/{config.LLM_RETRY_COUNT + 1})")
            except Exception as e:
                log.warning(f"Raw LLM call failed (attempt {attempt + 1}): {e}")
                if attempt == config.LLM_RETRY_COUNT:
                    raise
                # Use longer delay for rate limits (429)
                if "429" in str(e):
                    delay = 5.0 * (attempt + 1)
                    log.info(f"Rate limited — waiting {delay}s before retry")
                else:
                    delay = config.LLM_RETRY_DELAY * (attempt + 1)
                time.sleep(delay)
                continue
            time.sleep(config.LLM_RETRY_DELAY * (attempt + 1))

        return "My AI provider isn't responding — check your key or try again."

    def _raw_llm_call_single(self, prompt: str) -> str:
        """Single raw LLM call without retries."""
        if self.provider == "gemini":
            # Use a fresh chat for one-off planning calls
            import google.generativeai as genai
            model = genai.GenerativeModel(
                model_name=config.GEMINI_MODEL,
                generation_config=genai.GenerationConfig(
                    temperature=0.2,  # Low temp for planning
                    max_output_tokens=config.LLM_MAX_TOKENS,
                ),
            )
            response = model.generate_content(prompt)
            return response.text

        elif self.provider == "ollama":
            response = self._client.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.2},
            )
            return response["message"]["content"]

        elif self.provider == "openai":
            response = self._client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=config.LLM_MAX_TOKENS,
            )
            return response.choices[0].message.content

        elif self.provider == "openrouter":
            models_to_try = [config.OPENROUTER_MODEL]
            if hasattr(config, "OPENROUTER_FALLBACK_MODELS") and config.OPENROUTER_FALLBACK_MODELS:
                models_to_try.extend([m.strip() for m in config.OPENROUTER_FALLBACK_MODELS.split(",") if m.strip()])
                
            last_error = None
            for model_name in models_to_try:
                try:
                    response = self._client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.2,
                        max_tokens=config.LLM_MAX_TOKENS,
                    )
                    
                    if not hasattr(response, "choices") or not response.choices:
                        raise ValueError(f"Provider returned invalid response: {response}")
                    
                    content = response.choices[0].message.content
                    if content is None:
                        raise ValueError(f"Provider returned None content (model={model_name})")
                    return content
                except Exception as e:
                    log.warning(f"OpenRouter model {model_name} failed: {e}")
                    last_error = e
            
            if config.GEMINI_API_KEY:
                log.warning("All OpenRouter models failed. Falling back to Gemini.")
                self.provider = "gemini"
                self._client = None
                self._init_client()
                return self._raw_llm_call_single(prompt)
                
            raise last_error or ValueError("All OpenRouter models failed")

        return ""

    def _raw_llm_call_with_history(self, user_input: str) -> str:
        """Send a message using conversation history for context. Retries on empty/failed responses."""
        for attempt in range(config.LLM_RETRY_COUNT + 1):
            try:
                raw = self._raw_llm_call_with_history_single(user_input)
                if raw and raw.strip():
                    return raw
                log.warning(f"LLM returned empty (attempt {attempt + 1}/{config.LLM_RETRY_COUNT + 1})")
            except Exception as e:
                log.warning(f"LLM call with history failed (attempt {attempt + 1}): {e}")
                if attempt == config.LLM_RETRY_COUNT:
                    raise
                # Use longer delay for rate limits (429)
                if "429" in str(e):
                    delay = 5.0 * (attempt + 1)
                    log.info(f"Rate limited — waiting {delay}s before retry")
                else:
                    delay = config.LLM_RETRY_DELAY * (attempt + 1)
                time.sleep(delay)
                continue
            time.sleep(config.LLM_RETRY_DELAY * (attempt + 1))

        return "My AI provider isn't responding — check your key or try again."

    def _raw_llm_call_with_history_single(self, user_input: str) -> str:
        """Single LLM call with history, no retries."""
        if self.provider == "gemini":
            response = self._chat.send_message(user_input)
            return response.text

        elif self.provider == "ollama":
            messages = [{"role": "system", "content": self._build_system_prompt()}]
            messages.extend(self.conversation_history[-config.CONTEXT_WINDOW_SIZE * 2:])
            messages.append({"role": "user", "content": user_input})
            response = self._client.chat(
                model=config.OLLAMA_MODEL,
                messages=messages,
                options={"temperature": config.LLM_TEMPERATURE},
            )
            return response["message"]["content"]

        elif self.provider == "openai":
            messages = [{"role": "system", "content": self._build_system_prompt()}]
            messages.extend(self.conversation_history[-config.CONTEXT_WINDOW_SIZE * 2:])
            messages.append({"role": "user", "content": user_input})
            response = self._client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                temperature=config.LLM_TEMPERATURE,
                max_tokens=config.LLM_MAX_TOKENS,
            )
            return response.choices[0].message.content

        elif self.provider == "openrouter":
            messages = [{"role": "system", "content": self._build_system_prompt()}]
            messages.extend(self.conversation_history[-config.CONTEXT_WINDOW_SIZE * 2:])
            messages.append({"role": "user", "content": user_input})
            
            models_to_try = [config.OPENROUTER_MODEL]
            if hasattr(config, "OPENROUTER_FALLBACK_MODELS") and config.OPENROUTER_FALLBACK_MODELS:
                models_to_try.extend([m.strip() for m in config.OPENROUTER_FALLBACK_MODELS.split(",") if m.strip()])
                
            last_error = None
            for model_name in models_to_try:
                try:
                    response = self._client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        temperature=config.LLM_TEMPERATURE,
                        max_tokens=config.LLM_MAX_TOKENS,
                    )
                    
                    if not hasattr(response, "choices") or not response.choices:
                        raise ValueError(f"Provider returned invalid response: {response}")
                    
                    content = response.choices[0].message.content
                    if content is None:
                        raise ValueError(f"Provider returned None content (model={model_name})")
                    return content
                except Exception as e:
                    log.warning(f"OpenRouter model {model_name} failed: {e}")
                    last_error = e
                    
            if config.GEMINI_API_KEY:
                log.warning("All OpenRouter models failed. Falling back to Gemini.")
                self.provider = "gemini"
                self._client = None
                self._init_client()
                return self._raw_llm_call_with_history_single(user_input)
                
            raise last_error or ValueError("All OpenRouter models failed")

        return "I'm sorry, I'm not properly configured."

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def _get_context(self):
        """Lazy-initialise the PC context tracker (active window, time of day)."""
        if self._context is None:
            from memory.context import Context
            self._context = Context()
        return self._context

    def _enrich_with_memory(self, user_input: str) -> str:
        """Inject long-term memory and current PC context into the user message."""
        blocks = []

        try:
            blocks.append(f"[Context] {self._get_context().get_context_string()}")
        except Exception as e:
            log.debug(f"Context unavailable: {e}")

        if self._memory:
            memory_ctx = self._memory.get_memory_prompt(user_input)
            if memory_ctx:
                blocks.append(memory_ctx)

        if not blocks:
            return user_input
        return "\n".join(blocks) + f"\n\nUser says: {user_input}"

    def _parse_response(self, raw_response: str) -> dict:
        """Parse LLM response to extract action JSON from action block."""
        result = {"response": raw_response, "action": None, "params": None}

        action_pattern = r"```action\s*\n(.*?)```"
        match = re.search(action_pattern, raw_response, re.DOTALL)

        if match:
            try:
                action_json = json.loads(match.group(1).strip())
                result["action"] = action_json.get("action")
                result["params"] = action_json.get("params", {})
                result["response"] = re.sub(action_pattern, "", raw_response, flags=re.DOTALL).strip()
            except json.JSONDecodeError as e:
                log.warning(f"Failed to parse action JSON: {e}")

        return result

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history.clear()
        if self.provider == "gemini" and self._client:
            self._chat = self._client.start_chat(history=[])
        log.info("🗑️ Conversation history cleared")

    def get_history_summary(self) -> str:
        if not self.conversation_history:
            return "No conversation history yet."
        lines = []
        for msg in self.conversation_history[-10:]:
            role = "You" if msg["role"] == "user" else "Alex"
            content = msg["content"][:100]
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def get_current_plan(self) -> dict | None:
        """Return the plan for the request in flight, or None when idle."""
        with self._plan_lock:
            plan = self._current_plan
        return plan.to_dict() if plan else None
