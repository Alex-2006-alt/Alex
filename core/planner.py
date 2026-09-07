"""
ALEX — Task Planner
Breaks complex user requests into structured, executable step-by-step plans.
Uses a ReAct (Reason → Act → Observe → Reflect) agentic loop.
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from utils.logger import log
import config


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    """A single executable step in a plan."""
    id: int
    action: str
    params: dict
    description: str = ""
    depends_on: list[int] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 2)
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "params": self.params,
            "description": self.description,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": str(self.result)[:200] if self.result else None,
            "error": self.error,
            "duration": self.duration,
        }


@dataclass
class Plan:
    """A structured multi-step execution plan."""
    goal: str
    steps: list[Step]
    created_at: float = field(default_factory=time.time)
    status: str = "pending"   # pending | running | done | failed | cancelled
    final_response: str = ""

    def get_step(self, step_id: int) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def get_ready_steps(self) -> list[Step]:
        """Return steps whose dependencies are all complete."""
        ready = []
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            deps_done = all(
                (self.get_step(dep_id) and
                 self.get_step(dep_id).status == StepStatus.DONE)
                for dep_id in step.depends_on
            )
            if deps_done:
                ready.append(step)
        return ready

    def is_done(self) -> bool:
        return all(
            s.status in (StepStatus.DONE, StepStatus.FAILED, StepStatus.SKIPPED)
            for s in self.steps
        )

    def has_failures(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps)

    def summary(self) -> str:
        done = sum(1 for s in self.steps if s.status == StepStatus.DONE)
        failed = sum(1 for s in self.steps if s.status == StepStatus.FAILED)
        total = len(self.steps)
        return f"{done}/{total} steps done, {failed} failed"

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "status": self.status,
            "summary": self.summary(),
            "steps": [s.to_dict() for s in self.steps],
            "final_response": self.final_response,
        }


class Planner:
    """
    Generates and manages structured execution plans for complex tasks.
    Works with the Brain to decompose goals into tool-executable steps.
    """

    PLAN_PROMPT_TEMPLATE = """You are a planning assistant. The user wants to accomplish a complex task.
Break it down into a JSON plan with sequential or parallel steps.

AVAILABLE TOOLS:
{tool_descriptions}

USER GOAL: {goal}

CONTEXT:
{context}

PREVIOUS STEP RESULTS (if any):
{previous_results}

Return ONLY a valid JSON object in this exact format (no other text):
{{
  "reasoning": "Brief explanation of why you chose this plan",
  "steps": [
    {{
      "id": 1,
      "action": "tool_name",
      "params": {{"key": "value"}},
      "description": "What this step does",
      "depends_on": []
    }},
    {{
      "id": 2,
      "action": "another_tool",
      "params": {{"key": "value"}},
      "description": "What this step does",
      "depends_on": [1]
    }}
  ]
}}

RULES:
- Steps with empty depends_on can run in parallel
- Steps with depends_on:[1] must wait for step 1 to complete
- Use ONLY tools from the AVAILABLE TOOLS list
- Keep each step atomic and focused on ONE action
- Maximum {max_steps} steps
- If no action is needed (just a question), return {{"steps": [], "reasoning": "No action needed"}}

USING A PREVIOUS STEP'S OUTPUT:
Write {{{{step_N.result}}}} inside any param value and it is replaced with the
output of step N before the step runs. The step MUST list N in its depends_on.
Example — read a file, then email its contents:
  {{"id": 1, "action": "file_read", "params": {{"path": "C:/notes.txt"}}, "depends_on": []}}
  {{"id": 2, "action": "email_send", "params": {{"to": "me@example.com", "subject": "Notes", "body": "{{{{step_1.result}}}}"}}, "depends_on": [1]}}
"""

    REFLECT_PROMPT_TEMPLATE = """You are reviewing the results of executed plan steps.

ORIGINAL GOAL: {goal}
STEPS EXECUTED: {steps_summary}
CURRENT RESULTS: {results}

Based on these results:
1. Is the goal fully accomplished? 
2. Do we need additional steps?
3. What is the final response to give the user?

Return ONLY a JSON object:
{{
  "goal_accomplished": true/false,
  "additional_steps": [],
  "final_response": "The response to speak/show to the user"
}}
"""

    def __init__(self, llm_caller: Callable, tool_registry=None):
        """
        Args:
            llm_caller: Function that takes a prompt string and returns response string
            tool_registry: ToolRegistry instance with available tools
        """
        self.llm_caller = llm_caller
        self.tool_registry = tool_registry
        self.current_plan: Plan | None = None
        self._plan_listeners: list[Callable] = []

    def add_plan_listener(self, callback: Callable):
        """Register a callback to receive plan update events."""
        self._plan_listeners.append(callback)

    def _notify_listeners(self, event: str, data: dict):
        for cb in self._plan_listeners:
            try:
                cb(event, data)
            except Exception as e:
                log.warning(f"Plan listener error: {e}")

    def should_plan(self, user_input: str) -> bool:
        """
        Heuristic to decide if a request needs multi-step planning.
        Simple requests go through the fast single-step path.
        """
        if not config.AGENT_MODE:
            return False

        lower = user_input.lower().strip()

        # Exclusions: conversational queries should NEVER trigger the planner
        conversational_patterns = [
            "what can you do", "how are you", "who are you", "what are you",
            "hello", "hi ", "hey ", "thanks", "thank you", "help",
            "what's your name", "tell me about yourself", "good morning",
            "good evening", "good night", "how's it going", "what's up",
            "can you help", "are you there", "do you understand",
        ]
        if any(pat in lower for pat in conversational_patterns):
            return False

        # Simple questions (starting with question words, short) — skip planning
        if lower.startswith(("what ", "who ", "where ", "when ", "why ", "how ", "is ", "are ", "do ", "does ", "can ")):
            word_count = len(lower.split())
            if word_count < 20:
                return False

        # Keywords that suggest complexity
        complex_indicators = [
            "and then", "after that", "also", "furthermore",
            "research", "summarize", "create a report", "find all",
            "monitor", "every", "schedule", "background",
            "compare", "analyze", "organize", "batch",
            "download and", "search and", "open and",
            "multiple", "several", "list of", "for each",
        ]

        indicator_count = sum(1 for kw in complex_indicators if kw in lower)

        # Also check word count — long requests are usually complex
        word_count = len(lower.split())

        return indicator_count >= 2 or word_count > 25

    def create_plan(self, goal: str, context: str = "", previous_results: str = "") -> Plan | None:
        """
        Ask the LLM to create a step-by-step plan for the given goal.

        Returns:
            Plan object, or None if no planning needed (simple task)
        """
        tool_descriptions = self._get_tool_descriptions()

        prompt = self.PLAN_PROMPT_TEMPLATE.format(
            tool_descriptions=tool_descriptions,
            goal=goal,
            context=context,
            previous_results=previous_results or "None",
            max_steps=config.MAX_AGENT_STEPS,
        )

        log.info(f"🗺️ Planning for goal: {goal[:80]}")

        try:
            raw = self.llm_caller(prompt)
            plan_data = self._parse_json_response(raw)

            if not plan_data:
                log.warning("Planner returned unparseable response, falling back to single step")
                return None

            steps_data = plan_data.get("steps", [])
            reasoning = plan_data.get("reasoning", "")

            log.info(f"📋 Plan reasoning: {reasoning}")

            if not steps_data:
                log.info("Planner determined no action steps needed")
                return None

            steps = []
            for s in steps_data[:config.MAX_AGENT_STEPS]:
                steps.append(Step(
                    id=s.get("id", len(steps) + 1),
                    action=s.get("action", ""),
                    params=s.get("params", {}),
                    description=s.get("description", ""),
                    depends_on=s.get("depends_on", []),
                ))

            plan = Plan(goal=goal, steps=steps)
            self.current_plan = plan
            log.info(f"✅ Plan created: {len(steps)} steps")
            self._notify_listeners("plan_created", plan.to_dict())
            return plan

        except Exception as e:
            log.error(f"Planning failed: {e}")
            return None

    def reflect(self, plan: Plan) -> dict:
        """
        After executing all steps, ask the LLM to reflect on results
        and generate a final user-facing response.

        Returns dict with: goal_accomplished, additional_steps, final_response
        """
        steps_summary = "\n".join(
            f"  Step {s.id} ({s.action}): {s.status.value} — {s.description}"
            for s in plan.steps
        )

        results = "\n".join(
            f"  Step {s.id} result: {str(s.result)[:300]}"
            for s in plan.steps
            if s.result is not None
        )

        prompt = self.REFLECT_PROMPT_TEMPLATE.format(
            goal=plan.goal,
            steps_summary=steps_summary,
            results=results or "No results yet",
        )

        try:
            raw = self.llm_caller(prompt)
            reflection = self._parse_json_response(raw)

            if reflection:
                return reflection

        except Exception as e:
            log.error(f"Reflection failed: {e}")

        # Fallback response
        if plan.has_failures():
            return {
                "goal_accomplished": False,
                "additional_steps": [],
                "final_response": f"I completed some steps but ran into issues. {plan.summary()}",
            }
        return {
            "goal_accomplished": True,
            "additional_steps": [],
            "final_response": f"Done! I completed all {len(plan.steps)} steps successfully.",
        }

    def _get_tool_descriptions(self) -> str:
        """Get tool descriptions for the planning prompt."""
        if self.tool_registry and len(self.tool_registry):
            return self.tool_registry.get_descriptions_for_prompt()

        # No registry means nothing is callable. Listing the pre-migration
        # action names here just produced plans full of unknown tools.
        log.error("Planner has no tools available")
        return "(none — no tools are registered, so no plan can be executed)"

    def _parse_json_response(self, raw: str) -> dict | None:
        """Extract JSON from LLM response, handling markdown code fences."""
        import re

        # Try to extract JSON from code fences
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if fence_match:
            raw = fence_match.group(1).strip()

        # Try to find JSON object boundaries
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to find the JSON block
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass

        log.warning(f"Could not parse JSON from planner response: {raw[:200]}")
        return None
