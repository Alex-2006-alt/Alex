"""
Tests for the Brain: action-block parsing, step-result substitution, and the
reflection loop that lets a plan grow.
"""

import pytest

import config
from core.brain import Brain
from core.planner import Plan, Step, StepStatus
from core.tool_registry import ToolRegistry, ToolSpec, ToolResult, SafetyLevel


@pytest.fixture
def brain():
    """A Brain with no LLM client — only its pure helpers are exercised."""
    return Brain(provider="gemini")


class TestParseResponse:
    def test_plain_text_has_no_action(self, brain):
        result = brain._parse_response("I'm doing great, thanks for asking!")
        assert result["action"] is None
        assert result["response"] == "I'm doing great, thanks for asking!"

    def test_action_block_is_extracted(self, brain):
        raw = 'Opening Chrome!\n```action\n{"action": "app_open", "params": {"name": "chrome"}}\n```'
        result = brain._parse_response(raw)
        assert result["action"] == "app_open"
        assert result["params"] == {"name": "chrome"}

    def test_action_block_is_stripped_from_the_spoken_response(self, brain):
        raw = 'Sure thing!\n```action\n{"action": "app_open", "params": {}}\n```'
        assert brain._parse_response(raw)["response"] == "Sure thing!"

    def test_prose_after_the_block_is_kept(self, brain):
        raw = 'Before.\n```action\n{"action": "a", "params": {}}\n```\nAfter.'
        response = brain._parse_response(raw)["response"]
        assert "Before." in response and "After." in response

    def test_malformed_json_leaves_the_text_intact(self, brain):
        raw = 'Hmm\n```action\n{"action": "a", oops}\n```'
        result = brain._parse_response(raw)
        assert result["action"] is None
        assert "Hmm" in result["response"]

    def test_missing_params_defaults_to_empty_dict(self, brain):
        raw = '```action\n{"action": "screenshot_capture"}\n```'
        assert brain._parse_response(raw)["params"] == {}


class TestUnfulfilledPromiseRepair:
    """
    Under load the model returns "Opening YouTube for you!" with no action
    block, so Alex claims to have acted when nothing happened.
    """

    def test_response_with_an_action_is_left_alone(self, brain):
        result = {"response": "Opening YouTube!", "action": "web_open", "params": {}}
        assert brain._repair_unfulfilled_promise("p", dict(result)) == result

    def test_plain_conversation_is_left_alone(self, brain):
        result = {"response": "I'm doing great, thanks!", "action": None, "params": None}
        assert brain._repair_unfulfilled_promise("p", dict(result)) == result

    @pytest.mark.parametrize("text", [
        "Opening YouTube for you.",
        "Sure thing! Popping open Chrome.",
        "Playing that song now.",
        "Launching the app.",
        "Taking a screenshot for you.",
    ])
    def test_promises_are_detected(self, brain, text):
        assert brain._PROMISE_RE.search(text) is not None

    def test_retry_that_produces_an_action_is_used(self, brain, monkeypatch):
        monkeypatch.setattr(
            brain, "_raw_llm_call_with_history",
            lambda prompt: 'Opening it!\n```action\n{"action": "web_open", "params": {"url": "https://x.com"}}\n```',
        )
        repaired = brain._repair_unfulfilled_promise(
            "open x", {"response": "Opening X for you.", "action": None, "params": None}
        )
        assert repaired["action"] == "web_open"

    def test_unrecoverable_promise_becomes_an_honest_answer(self, brain, monkeypatch):
        monkeypatch.setattr(brain, "_raw_llm_call_with_history", lambda prompt: "Opening it now!")
        repaired = brain._repair_unfulfilled_promise(
            "open x", {"response": "Opening X for you.", "action": None, "params": None}
        )
        assert repaired["action"] is None
        assert "couldn't actually carry it out" in repaired["response"]

    def test_a_failing_retry_still_produces_an_honest_answer(self, brain, monkeypatch):
        def boom(prompt):
            raise RuntimeError("provider down")

        monkeypatch.setattr(brain, "_raw_llm_call_with_history", boom)
        repaired = brain._repair_unfulfilled_promise(
            "open x", {"response": "Opening X for you.", "action": None, "params": None}
        )
        assert "couldn't actually carry it out" in repaired["response"]


class TestResolveParams:
    """{{step_N.result}} substitution — without it, depends_on only sequences."""

    def test_reference_is_replaced(self, brain):
        params = {"body": "{{step_1.result}}"}
        assert brain._resolve_params(params, {1: "file contents"}) == {"body": "file contents"}

    def test_shorthand_without_dot_result(self, brain):
        assert brain._resolve_params("{{step_2}}", {2: "x"}) == "x"

    def test_reference_embedded_in_a_sentence(self, brain):
        out = brain._resolve_params("Found: {{step_1.result}} today", {1: "42"})
        assert out == "Found: 42 today"

    def test_multiple_references(self, brain):
        out = brain._resolve_params("{{step_1.result}} and {{step_2.result}}", {1: "a", 2: "b"})
        assert out == "a and b"

    def test_nested_dicts_and_lists(self, brain):
        params = {"outer": {"inner": ["{{step_1.result}}", "literal"]}}
        resolved = brain._resolve_params(params, {1: "X"})
        assert resolved == {"outer": {"inner": ["X", "literal"]}}

    def test_non_string_values_pass_through(self, brain):
        params = {"count": 5, "flag": True, "nothing": None}
        assert brain._resolve_params(params, {}) == params

    def test_unknown_step_is_left_visible(self, brain):
        """A blanked reference would silently send an empty body."""
        assert brain._resolve_params("{{step_9.result}}", {1: "a"}) == "{{step_9.result}}"

    def test_whitespace_inside_the_braces_is_tolerated(self, brain):
        assert brain._resolve_params("{{ step_1.result }}", {1: "ok"}) == "ok"

    def test_text_without_references_is_unchanged(self, brain):
        assert brain._resolve_params("plain text", {1: "a"}) == "plain text"


class TestAppendSteps:
    def _plan(self, count=2):
        return Plan(goal="g", steps=[
            Step(id=i, action="a", params={}, status=StepStatus.DONE)
            for i in range(1, count + 1)
        ])

    def test_steps_are_appended_with_fresh_ids(self, brain):
        plan = self._plan()
        added = brain._append_steps(plan, [{"action": "web_search", "params": {"query": "x"}}])
        assert added == 1
        assert len(plan.steps) == 3
        assert plan.steps[-1].id == 3
        assert plan.steps[-1].status == StepStatus.PENDING

    def test_total_is_capped_at_max_agent_steps(self, brain, monkeypatch):
        monkeypatch.setattr(config, "MAX_AGENT_STEPS", 3)
        plan = self._plan(2)
        added = brain._append_steps(plan, [{"action": "a"}, {"action": "b"}, {"action": "c"}])
        assert added == 1
        assert len(plan.steps) == 3

    def test_a_full_plan_accepts_nothing(self, brain, monkeypatch):
        monkeypatch.setattr(config, "MAX_AGENT_STEPS", 2)
        plan = self._plan(2)
        assert brain._append_steps(plan, [{"action": "a"}]) == 0

    def test_steps_without_an_action_are_ignored(self, brain):
        plan = self._plan()
        assert brain._append_steps(plan, [{"description": "think about it"}]) == 0


class TestPlanExecution:
    """End-to-end over _execute_plan with a stub registry."""

    def _brain_with_tools(self, fn):
        brain = Brain(provider="gemini")
        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="probe", description="test", fn=fn, parameters={},
            safety=SafetyLevel.SAFE, category="testing",
        ))
        brain.set_tool_registry(registry)
        return brain

    def test_results_flow_from_one_step_to_the_next(self):
        seen = []

        def probe(params):
            seen.append(params)
            return f"out-{len(seen)}"

        brain = self._brain_with_tools(probe)
        plan = Plan(goal="g", steps=[
            Step(id=1, action="probe", params={}),
            Step(id=2, action="probe", params={"input": "{{step_1.result}}"}, depends_on=[1]),
        ])

        brain._execute_plan(plan)

        assert seen[1] == {"input": "out-1"}, "step 2 did not receive step 1's output"
        assert all(s.status == StepStatus.DONE for s in plan.steps)

    def test_a_failing_step_skips_its_dependents(self):
        def probe(params):
            raise RuntimeError("nope")

        brain = self._brain_with_tools(probe)
        plan = Plan(goal="g", steps=[
            Step(id=1, action="probe", params={}),
            Step(id=2, action="probe", params={}, depends_on=[1]),
        ])

        brain._execute_plan(plan)

        assert plan.steps[0].status == StepStatus.FAILED
        assert plan.steps[1].status == StepStatus.SKIPPED
        assert plan.has_failures() is True

    def test_confirm_level_steps_are_denied_without_a_channel(self):
        ran = []
        brain = Brain(provider="gemini")
        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="danger", description="test", fn=lambda p: ran.append(p),
            parameters={}, safety=SafetyLevel.CONFIRM, category="testing",
        ))
        brain.set_tool_registry(registry)

        plan = Plan(goal="g", steps=[Step(id=1, action="danger", params={})])
        brain._execute_plan(plan)

        assert ran == [], "a plan step ran a CONFIRM tool with no confirmation channel"
        assert plan.steps[0].status == StepStatus.FAILED

    def test_confirm_level_steps_run_when_a_channel_approves(self):
        ran = []
        brain = Brain(provider="gemini")
        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="danger", description="test", fn=lambda p: ran.append(p) or "done",
            parameters={}, safety=SafetyLevel.CONFIRM, category="testing",
        ))
        brain.set_tool_registry(registry)
        brain.set_confirm_callback(lambda name, params: True)

        plan = Plan(goal="g", steps=[Step(id=1, action="danger", params={})])
        brain._execute_plan(plan)

        assert len(ran) == 1
        assert plan.steps[0].status == StepStatus.DONE

    def test_agent_auto_confirm_opts_in(self, monkeypatch):
        monkeypatch.setattr(config, "AGENT_AUTO_CONFIRM", True)
        ran = []
        brain = Brain(provider="gemini")
        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="danger", description="test", fn=lambda p: ran.append(p) or "done",
            parameters={}, safety=SafetyLevel.CONFIRM, category="testing",
        ))
        brain.set_tool_registry(registry)

        brain._execute_plan(Plan(goal="g", steps=[Step(id=1, action="danger", params={})]))
        assert len(ran) == 1

    def test_no_registry_fails_the_step_cleanly(self):
        brain = Brain(provider="gemini")
        plan = Plan(goal="g", steps=[Step(id=1, action="probe", params={})])
        brain._execute_plan(plan)
        assert plan.steps[0].status == StepStatus.FAILED
        assert "ToolRegistry" in plan.steps[0].error


class TestCurrentPlanLifecycle:
    def test_idle_brain_reports_no_plan(self, brain):
        assert brain.get_current_plan() is None

    def test_a_finished_plan_is_still_readable(self, brain):
        brain._current_plan = Plan(goal="g", steps=[Step(id=1, action="a", params={})])
        assert brain.get_current_plan()["goal"] == "g"
