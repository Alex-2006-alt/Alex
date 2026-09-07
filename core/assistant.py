"""
ALEX — Main Assistant Orchestrator (Upgraded)
Ties together: wake word → listen → think (+ plan) → act → speak
Integrates: ToolRegistry, LongTermMemory, TaskManager, SystemMonitor
"""

import time
import sys

from utils.logger import log
import config

from core.listener import Listener
from core.speaker import Speaker
from core.brain import Brain
from core.wake_word import WakeWordDetector
from core.command_dispatcher import CommandDispatcher
class Assistant:
    """
    The upgraded ALEX assistant.

    Pipeline:
    1. Wait for wake word ("Hey Alex")
    2. Listen to user speech
    3. Transcribe with Whisper
    4. Think — fast (single action) or agentic (multi-step plan)
    5. Execute tool(s) via ToolRegistry
    6. Speak the response

    New in this version:
    - ToolRegistry: dynamic tool system
    - LongTermMemory: persistent facts & preferences
    - TaskManager: background tasks & monitors
    - SystemMonitor: CPU/RAM/disk watchers
    - Planner: multi-step ReAct agentic loop
    """

    def __init__(self, use_wake_word: bool = True, input_mode: str = "voice"):
        self.use_wake_word = use_wake_word
        self.input_mode = input_mode  # "voice" or "text"
        self._running = False

        log.info("=" * 60)
        log.info(f"  🤖 Initializing {config.ASSISTANT_NAME} (Upgraded)...")
        log.info("=" * 60)

        # Core I/O
        self.listener = Listener()
        self.speaker = Speaker()

        # Brain (upgraded with agentic mode)
        self.brain = Brain()

        # Command dispatcher (fast path — bypasses LLM for known commands)
        self.dispatcher = CommandDispatcher()

        # Initialize integrations
        self._init_tool_registry()
        self._init_memory()
        self._init_task_manager()

        # Connect brain to integrations
        self.brain.set_tool_registry(self._tool_registry)
        self.brain.set_memory(self._memory)
        self.brain.set_task_manager(self._task_manager)

        # Wake word
        if self.use_wake_word:
            self.wake_detector = WakeWordDetector()
        else:
            self.wake_detector = None

        log.info(f"✅ {config.ASSISTANT_NAME} is ready!")
        log.info(f"   🔧 Tools: {len(self._tool_registry)} registered")
        log.info(f"   💾 Memory: {self._memory.stats()['facts']} facts stored")
        log.info(f"   🗺️ Agent mode: {config.AGENT_MODE}")
        log.info(f"   🎧 Input mode: {self.input_mode}")
        log.info(f"   📋 Commands: {len(self.dispatcher.list_commands())} registered")

    # ─── INITIALIZATION ───────────────────────────────────────────────────────

    def _init_tool_registry(self):
        """Initialize the ToolRegistry and load all tools."""
        try:
            from core.tool_registry import ToolRegistry
            import tools  # noqa: F401 — triggers all @tool registrations

            self._tool_registry = ToolRegistry.get_instance()
            log.info(f"✅ ToolRegistry: {len(self._tool_registry)} tools")
        except Exception as e:
            log.error(f"ToolRegistry init failed: {e}")
            self._tool_registry = None

    def _init_memory(self):
        """Initialize long-term memory."""
        try:
            from memory.long_term import LongTermMemory
            self._memory = LongTermMemory()
            stats = self._memory.stats()
            log.info(f"✅ LongTermMemory: {stats['facts']} facts, {stats['tasks']} tasks")
        except Exception as e:
            log.warning(f"LongTermMemory init failed: {e}")
            self._memory = None

    def _init_task_manager(self):
        """Initialize the task manager and system monitor."""
        try:
            from core.task_manager import TaskManager
            from core.monitor import SystemMonitor

            self._task_manager = TaskManager(alert_callback=self._on_monitor_alert)
            self._monitor = SystemMonitor(alert_callback=self._on_monitor_alert)
            self._monitor.set_task_manager(self._task_manager)

            log.info("✅ TaskManager and SystemMonitor ready")
        except Exception as e:
            log.warning(f"TaskManager init failed: {e}")
            self._task_manager = None
            self._monitor = None

    def _on_monitor_alert(self, message: str):
        """Called by monitors when a threshold is exceeded."""
        log.warning(f"🚨 Alert: {message}")
        self.speaker.say(f"Alert! {message}")
        # Show desktop notification if possible
        try:
            from tools.notification_tools import notify
            notify({"title": "⚠️ Alex Alert", "message": message})
        except Exception:
            pass

    # ─── LISTEN ADAPTERS ──────────────────────────────────────────────────────

    def listen_text(self) -> str | None:
        """Read one line from stdin. Returns stripped text or None."""
        try:
            raw = input(f"\n  You: ").strip()
            if raw:
                log.info(f"⌨️ Text input: \"{raw}\"")
                return raw
            return None
        except (EOFError, KeyboardInterrupt):
            return None

    def listen_voice(self) -> str | None:
        """Capture microphone audio and transcribe via Whisper."""
        return self.listener.listen()

    def listen(self) -> str | None:
        """Route to the correct adapter based on ``self.input_mode``."""
        if self.input_mode == "text":
            return self.listen_text()
        return self.listen_voice()

    # ─── MAIN LOOP ────────────────────────────────────────────────────────────

    def run(self):
        """Start the main assistant loop."""
        self._running = True

        greeting = f"Hello! I'm {config.ASSISTANT_NAME}, your upgraded AI assistant. I can now handle complex multi-step tasks. How can I help?"
        print(f"\n{'='*65}")
        print(f"  🤖 {config.ASSISTANT_NAME} — Advanced Personal AI Assistant")
        print(f"  🧠 Brain: {config.LLM_PROVIDER} | Agent Mode: {config.AGENT_MODE}")
        print(f"  🎤 STT: Whisper ({config.WHISPER_MODEL_SIZE})")
        print(f"  🔊 TTS: {config.TTS_ENGINE}")
        print(f"  🔧 Tools: {len(self._tool_registry) if self._tool_registry else 'legacy'} registered")
        if self.use_wake_word:
            print(f"  🔑 Wake word: \"{config.WAKE_WORD}\"")
        print(f"  ⛔ Press Ctrl+C to quit")
        print(f"{'='*65}\n")

        self.speaker.say(greeting)

        try:
            while self._running:
                try:
                    self._interaction_loop()
                except KeyboardInterrupt:
                    raise  # Let the outer handler catch it
                except Exception as e:
                    log.error(f"Interaction loop error (recovering): {e}")
                    try:
                        self.speaker.say("Sorry, something went wrong. Let me try again.")
                    except Exception:
                        pass
                    time.sleep(1)  # Brief pause before retrying
        except KeyboardInterrupt:
            self.shutdown()

    def _interaction_loop(self):
        """Single interaction cycle: listen → think → act → speak."""

        # Step 1: Wait for wake word
        if self.use_wake_word and self.wake_detector:
            self.wake_detector.wait_for_wake_word()
            self.speaker.say("Yes?", block=True)

        # Step 2: Listen (via adapter)
        user_input = self.listen()
        if not user_input:
            if not self.use_wake_word:
                time.sleep(0.5)
            return

        # Step 3: Special commands check
        if self._handle_special_commands(user_input):
            return

        # Step 4: Try command dispatcher first (fast path)
        dispatched = self.dispatcher.dispatch(user_input)
        if dispatched is not None:
            self.speaker.say(dispatched)
            return

        # Step 5: Think via LLM (fast or agentic)
        result = self.brain.think(user_input)

        # Guard: if brain returned nothing useful, give a fallback
        if not result or not result.get("response", "").strip():
            log.warning("Brain returned empty result, using fallback")
            result = {
                "response": "I'm sorry, I didn't get a response from my AI backend. Could you try again?",
                "action": None,
                "params": None,
            }

        # Step 6: Execute action (fast path only — agentic path executes internally)
        if result.get("action"):
            if self._tool_registry:
                from core.tool_registry import ToolResult
                tool_result = self._tool_registry.execute(
                    result["action"],
                    result.get("params") or {},
                    confirm_callback=self._voice_confirm_tool,
                )
                action_response = tool_result.to_response()
            else:
                action_response = "Error: ToolRegistry is not initialized."

            # Only use technical action_response as fallback if LLM gave no conversational response
            if not result.get("response") or not result["response"].strip():
                result["response"] = action_response

        # Step 6: Speak response
        if result.get("response"):
            self.speaker.say(result["response"])

    def _voice_confirm(self, action: str, params: dict) -> bool:
        """Ask user for voice confirmation of dangerous actions (legacy)."""
        self.speaker.say(
            f"Warning: you're asking me to {action}. "
            f"This could be dangerous. Should I proceed? Say yes or no."
        )
        response = self.listener.listen()
        if response:
            response_lower = response.lower()
            if any(w in response_lower for w in ["yes", "yeah", "sure", "go ahead", "do it", "confirm"]):
                log.info("✅ User confirmed dangerous action")
                return True
        log.info("🚫 User denied dangerous action")
        self.speaker.say("Okay, I cancelled that action.")
        return False

    def _voice_confirm_tool(self, tool_name: str, params: dict) -> bool:
        """Voice confirmation for CONFIRM-safety-level tools."""
        return self._voice_confirm(tool_name, params)

    def _handle_special_commands(self, text: str) -> bool:
        """Handle built-in commands that don't need the LLM."""
        text_lower = text.lower().strip()

        # Exit
        if text_lower in ["quit", "exit", "stop", "goodbye", "bye", "shut down alex"]:
            self.speaker.say("Goodbye! Have a great day!")
            self.shutdown()
            return True

        # Clear history
        if text_lower in ["clear history", "forget everything", "reset"]:
            self.brain.clear_history()
            self.speaker.say("I've cleared my conversation history. Starting fresh!")
            return True

        # Clear memory
        if "forget what you know about me" in text_lower or "clear my memory" in text_lower:
            if self._memory:
                facts = self._memory.get_all_facts()
                for f in facts:
                    self._memory.forget(f.key)
            self.speaker.say("I've cleared all stored information about you.")
            return True

        # Cancel shutdown
        if "cancel shutdown" in text_lower or "abort shutdown" in text_lower:
            import os
            os.system("shutdown /a")
            self.speaker.say("Shutdown cancelled.")
            return True

        # System status
        if text_lower in ["status", "system status", "how is the system"]:
            from utils.system_info import get_system_summary, format_system_info_for_speech
            info = get_system_summary()
            self.speaker.say(format_system_info_for_speech(info))
            return True

        # Task status
        if "what tasks" in text_lower or "running tasks" in text_lower or "background tasks" in text_lower:
            if self._task_manager:
                summary = self._task_manager.get_summary()
                self.speaker.say(summary)
            else:
                self.speaker.say("Task manager is not available.")
            return True

        # Cancel all tasks
        if "cancel all tasks" in text_lower or "stop all tasks" in text_lower:
            if self._task_manager:
                self._task_manager.cancel_all()
                self.speaker.say("All background tasks cancelled.")
            return True

        # Memory summary
        if "what do you know about me" in text_lower or "my profile" in text_lower:
            if self._memory:
                profile = self._memory.get_user_profile()
                if profile:
                    facts_text = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in profile.items())
                    self.speaker.say(f"Here's what I know about you: {facts_text}")
                else:
                    self.speaker.say("I don't have any stored information about you yet.")
            return True

        return False

    def process_text_full(self, text: str) -> dict:
        """Process a text command and return rich execution metadata."""
        log.info(f"📝 Processing text: \"{text}\"")

        if self._handle_special_commands(text):
            return {"response": "Special command handled.", "action": "built_in", "params": {}}

        # Try command dispatcher first (fast path)
        dispatched = self.dispatcher.dispatch(text)
        if dispatched is not None:
            return {"response": dispatched, "action": "dispatcher", "params": {}}

        result = self.brain.think(text)
        action_response = None

        if result.get("action"):
            if self._tool_registry:
                tool_result = self._tool_registry.execute(result["action"], result.get("params") or {})
                action_response = tool_result.to_response()
            else:
                action_response = "Error: ToolRegistry is not initialized."
            # Only use technical action_response as fallback if LLM gave no conversational response
            if not result.get("response") or not result["response"].strip():
                result["response"] = action_response

        return {
            "response": result.get("response", ""),
            "action": result.get("action"),
            "params": result.get("params"),
            "action_result": action_response,
            "plan": self.brain.get_current_plan(),
        }

    def process_text(self, text: str) -> str:
        """Process a text command (returns string response)."""
        res = self.process_text_full(text)
        return res.get("response", "")

    def get_status(self) -> dict:
        """Get current status of all subsystems."""
        status = {
            "name": config.ASSISTANT_NAME,
            "provider": config.LLM_PROVIDER,
            "agent_mode": config.AGENT_MODE,
            "tools": len(self._tool_registry) if self._tool_registry else 0,
            "running": self._running,
        }
        if self._memory:
            status["memory"] = self._memory.stats()
        if self._task_manager:
            tasks = self._task_manager.list_tasks()
            status["background_tasks"] = len(tasks)
        if self.brain.get_current_plan():
            status["current_plan"] = self.brain.get_current_plan()
        return status

    def shutdown(self):
        """Gracefully shut down."""
        log.info(f"👋 {config.ASSISTANT_NAME} shutting down...")
        self._running = False

        if self._task_manager:
            self._task_manager.cancel_all()

        if self.wake_detector:
            self.wake_detector.stop()

        if self._memory:
            self._memory.close()

        self.speaker.stop()
        log.info("✅ Shutdown complete")
        sys.exit(0)
