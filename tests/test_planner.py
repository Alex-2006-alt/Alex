"""
Tests for ALEX Planner — routing heuristic, plan parsing, and the dependency
ordering that drives step execution.
"""

import json

import pytest

import config
from core.planner import Planner, Plan, Step, StepStatus


def make_planner(llm_response="{}"):
    """A planner whose LLM returns a canned string."""
    calls = []

    def caller(prompt):
        calls.append(prompt)
        return llm_response

    planner = Planner(llm_caller=caller, tool_registry=None)
    planner.calls = calls
    return planner


class TestShouldPlan:
    """Routing: cheap conversation must not pay for a planning round-trip."""

    def setup_method(self):
        self.planner = make_planner()

    @pytest.mark.parametrize("text", [
        "hello",
        "how are you",
        "who are you",
        "what can you do",
        "thanks",
        "good morning",
        "what's your name",
    ])
    def test_conversation_skips_the_planner(self, text):
        assert self.planner.should_plan(text) is False

    @pytest.mark.parametrize("text", [
        "what time is it",
        "how much RAM do I have",
        "can you open chrome",
        "is my battery charging",
    ])
    def test_short_questions_skip_the_planner(self, text):
        assert self.planner.should_plan(text) is False

    @pytest.mark.parametrize("text", [
        "research the top python web frameworks and summarize them into a report",
        "find all pdf files in downloads and then organize them into folders",
        "monitor my cpu every 5 minutes and alert me if it goes above 90",
    ])
    def test_multi_step_requests_use_the_planner(self, text):
        assert self.planner.should_plan(text) is True

    def test_agent_mode_off_disables_planning(self, monkeypatch):
        monkeypatch.setattr(config, "AGENT_MODE", False)
        assert self.planner.should_plan("research and summarize and compare") is False


class TestParseJsonResponse:
    """LLMs wrap JSON in fences and prose; the parser has to cope."""

    def setup_method(self):
        self.planner = make_planner()

    def test_bare_json(self):
        assert self.planner._parse_json_response('{"steps": []}') == {"steps": []}

    def test_json_in_a_fenced_block(self):
        raw = 'Here you go:\n```json\n{"steps": [], "reasoning": "none"}\n```'
        assert self.planner._parse_json_response(raw)["reasoning"] == "none"

    def test_json_in_an_unlabelled_fence(self):
        assert self.planner._parse_json_response('```\n{"a": 1}\n```') == {"a": 1}

    def test_json_surrounded_by_prose(self):
        raw = 'Sure! {"steps": [], "reasoning": "hi"} Hope that helps.'
        assert self.planner._parse_json_response(raw)["reasoning"] == "hi"

    def test_unparseable_returns_none(self):
        assert self.planner._parse_json_response("I couldn't do that, sorry.") is None

    def test_empty_returns_none(self):
        assert self.planner._parse_json_response("") is None


class TestCreatePlan:
    def _plan_json(self, steps):
        return json.dumps({"reasoning": "test", "steps": steps})

    def test_steps_become_step_objects(self):
        planner = make_planner(self._plan_json([
            {"id": 1, "action": "web_search", "params": {"query": "x"}, "depends_on": []},
            {"id": 2, "action": "file_write", "params": {"path": "a"}, "depends_on": [1]},
        ]))
        plan = planner.create_plan("do a thing")

        assert len(plan.steps) == 2
        assert plan.steps[0].action == "web_search"
        assert plan.steps[1].depends_on == [1]
        assert all(s.status == StepStatus.PENDING for s in plan.steps)

    def test_empty_steps_returns_none(self):
        planner = make_planner(self._plan_json([]))
        assert planner.create_plan("just chatting") is None

    def test_unparseable_response_returns_none(self):
        assert make_planner("sorry, no").create_plan("do a thing") is None

    def test_step_count_is_capped(self, monkeypatch):
        monkeypatch.setattr(config, "MAX_AGENT_STEPS", 3)
        steps = [{"id": i, "action": "web_search", "params": {}} for i in range(1, 11)]
        plan = make_planner(self._plan_json(steps)).create_plan("do many things")
        assert len(plan.steps) == 3

    def test_prompt_documents_the_step_reference_syntax(self):
        planner = make_planner(self._plan_json([]))
        planner.create_plan("goal")
        assert "{{step_1.result}}" in planner.calls[0]

    def test_no_registry_means_no_tools_are_advertised(self):
        planner = make_planner(self._plan_json([]))
        planner.create_plan("goal")
        # The pre-migration action names must not reappear in the prompt
        assert "open_app" not in planner.calls[0]
        assert "file_operation" not in planner.calls[0]


class TestDependencyOrdering:
    def _plan(self):
        return Plan(goal="g", steps=[
            Step(id=1, action="a", params={}),
            Step(id=2, action="b", params={}, depends_on=[1]),
            Step(id=3, action="c", params={}, depends_on=[1]),
            Step(id=4, action="d", params={}, depends_on=[2, 3]),
        ])

    def test_only_independent_steps_are_ready_first(self):
        plan = self._plan()
        assert [s.id for s in plan.get_ready_steps()] == [1]

    def test_dependents_unlock_together(self):
        plan = self._plan()
        plan.get_step(1).status = StepStatus.DONE
        assert [s.id for s in plan.get_ready_steps()] == [2, 3]

    def test_a_failed_dependency_blocks_its_dependents(self):
        plan = self._plan()
        plan.get_step(1).status = StepStatus.FAILED
        assert plan.get_ready_steps() == []

    def test_all_dependencies_must_be_done(self):
        plan = self._plan()
        plan.get_step(1).status = StepStatus.DONE
        plan.get_step(2).status = StepStatus.DONE
        assert [s.id for s in plan.get_ready_steps()] == [3]

    def test_missing_dependency_id_blocks_rather_than_crashes(self):
        plan = Plan(goal="g", steps=[Step(id=1, action="a", params={}, depends_on=[99])])
        assert plan.get_ready_steps() == []

    def test_is_done_only_when_every_step_settled(self):
        plan = self._plan()
        assert plan.is_done() is False
        for s in plan.steps:
            s.status = StepStatus.DONE
        assert plan.is_done() is True

    def test_skipped_and_failed_count_as_settled(self):
        plan = self._plan()
        plan.steps[0].status = StepStatus.DONE
        plan.steps[1].status = StepStatus.FAILED
        plan.steps[2].status = StepStatus.SKIPPED
        plan.steps[3].status = StepStatus.SKIPPED
        assert plan.is_done() is True
        assert plan.has_failures() is True


class TestReflectFallback:
    def test_unparseable_reflection_falls_back_to_success(self):
        planner = make_planner("not json")
        plan = Plan(goal="g", steps=[Step(id=1, action="a", params={}, status=StepStatus.DONE)])
        reflection = planner.reflect(plan)
        assert reflection["goal_accomplished"] is True
        assert reflection["final_response"]

    def test_failures_are_reported_in_the_fallback(self):
        planner = make_planner("not json")
        plan = Plan(goal="g", steps=[Step(id=1, action="a", params={}, status=StepStatus.FAILED)])
        assert planner.reflect(plan)["goal_accomplished"] is False
