"""
Tests for the Flask API surface, driven with a stub assistant so no LLM,
microphone or Whisper model is needed.
"""

import pytest

import server
from core.tool_registry import ToolRegistry, ToolSpec, ToolResult, SafetyLevel


class StubMemory:
    def __init__(self):
        self.facts = {}
        self.deleted = []

    def get_all_facts(self, category=None):
        class F:
            def __init__(self, k, v):
                self.key, self.value, self.category, self.confidence = k, v, "general", 1.0
        return [F(k, v) for k, v in self.facts.items()]

    def stats(self):
        return {"facts": len(self.facts), "tasks": 0}

    def remember(self, key, value, category="general"):
        self.facts[key] = value

    def forget(self, key):
        self.deleted.append(key)
        return self.facts.pop(key, None) is not None

    def get_task_history(self, limit=10):
        return [{"goal": "g", "status": "done"}]


class StubTaskManager:
    def __init__(self):
        self.cancelled = []

    def list_tasks(self, include_done=False):
        class T:
            def to_dict(self):
                return {"id": "t1", "status": "running"}
        return [T()]

    def cancel(self, task_id):
        self.cancelled.append(task_id)
        return True


class StubBrain:
    def __init__(self):
        self.plan = None

    def get_current_plan(self):
        return self.plan


class StubAssistant:
    def __init__(self):
        self.brain = StubBrain()
        self._memory = StubMemory()
        self._task_manager = StubTaskManager()
        self._tool_registry = ToolRegistry()
        self.last_confirm_callback = "unset"

        self._tool_registry.register(ToolSpec(
            name="safe_probe", description="d", fn=lambda p: "probed",
            parameters={}, safety=SafetyLevel.SAFE, category="testing",
        ))
        self.ran_dangerous = []
        self._tool_registry.register(ToolSpec(
            name="danger_probe", description="d",
            fn=lambda p: self.ran_dangerous.append(p) or "boom",
            parameters={}, safety=SafetyLevel.CONFIRM, category="testing",
        ))

    def process_text_full(self, text, confirm_callback=None):
        self.last_confirm_callback = confirm_callback
        return {"response": f"echo: {text}", "action": None, "params": None,
                "action_result": None, "plan": None}

    def get_status(self):
        return {"name": "Alex", "tools": len(self._tool_registry), "running": True}


@pytest.fixture
def stub(monkeypatch):
    assistant = StubAssistant()
    monkeypatch.setattr(server, "_get_assistant", lambda: assistant)
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c, assistant
    with server._pending_lock:
        for entry in server._pending.values():
            entry["event"].set()
        server._pending.clear()


class TestChat:
    def test_message_is_echoed_back(self, stub):
        client, _ = stub
        body = client.post("/api/chat", json={"message": "hello"}).get_json()
        assert body["response"] == "echo: hello"

    def test_missing_message_is_a_400(self, stub):
        client, _ = stub
        assert client.post("/api/chat", json={}).status_code == 400

    def test_blank_message_is_a_400(self, stub):
        client, _ = stub
        assert client.post("/api/chat", json={"message": "   "}).status_code == 400

    def test_a_confirmation_channel_is_always_supplied(self, stub):
        """Without this, CONFIRM tools would be denied outright on the web."""
        client, assistant = stub
        client.post("/api/chat", json={"message": "hi"})
        assert assistant.last_confirm_callback is server._request_confirmation

    def test_an_assistant_error_becomes_a_500_with_a_spoken_response(self, stub, monkeypatch):
        client, assistant = stub

        def boom(text, confirm_callback=None):
            raise RuntimeError("brain exploded")

        monkeypatch.setattr(assistant, "process_text_full", boom)
        resp = client.post("/api/chat", json={"message": "hi"})
        assert resp.status_code == 500
        assert "brain exploded" in resp.get_json()["response"]


class TestActionEndpoint:
    def test_safe_tool_runs(self, stub):
        client, _ = stub
        body = client.post("/api/action", json={"action": "safe_probe"}).get_json()
        assert body["success"] is True
        assert body["result"] == "probed"

    def test_unknown_tool_reports_failure(self, stub):
        client, _ = stub
        body = client.post("/api/action", json={"action": "no_such_tool"}).get_json()
        assert body["success"] is False

    def test_missing_action_is_a_400(self, stub):
        client, _ = stub
        assert client.post("/api/action", json={}).status_code == 400

    def test_dangerous_tool_is_not_executed_without_approval(self, stub, monkeypatch):
        """Regression: /api/action used to be an unguarded remote shell."""
        client, assistant = stub
        monkeypatch.setattr(server.config, "CONFIRMATION_TIMEOUT", 1)
        body = client.post("/api/action", json={"action": "danger_probe"}).get_json()
        assert body["success"] is False
        assert assistant.ran_dangerous == []


class TestReadEndpoints:
    def test_status(self, stub):
        client, _ = stub
        body = client.get("/api/status").get_json()
        assert body["status"] == "online"
        assert "boot" in body

    def test_actions_lists_registered_tools(self, stub):
        client, _ = stub
        body = client.get("/api/actions").get_json()
        assert "safe_probe" in body["tools"]
        assert body["count"] == 2

    def test_assistant_status(self, stub):
        client, _ = stub
        assert client.get("/api/assistant-status").get_json()["name"] == "Alex"

    def test_plan_is_idle_when_none_is_running(self, stub):
        client, _ = stub
        assert client.get("/api/plan").get_json()["status"] == "idle"

    def test_plan_is_returned_when_one_is_active(self, stub):
        client, assistant = stub
        assistant.brain.plan = {"goal": "do a thing", "status": "running"}
        assert client.get("/api/plan").get_json()["goal"] == "do a thing"

    def test_tasks(self, stub):
        client, _ = stub
        body = client.get("/api/tasks").get_json()
        assert body["count"] == 1

    def test_task_history(self, stub):
        client, _ = stub
        assert len(client.get("/api/task-history").get_json()["history"]) == 1

    def test_removed_plugins_endpoint_is_gone(self, stub):
        client, _ = stub
        assert client.get("/api/plugins").status_code == 404


class TestMemoryEndpoints:
    def test_set_then_get(self, stub):
        client, _ = stub
        client.post("/api/memory", json={"key": "name", "value": "Sam"})
        body = client.get("/api/memory").get_json()
        assert {"key": "name", "value": "Sam", "category": "general", "confidence": 1.0} in body["facts"]

    def test_set_requires_key_and_value(self, stub):
        client, _ = stub
        assert client.post("/api/memory", json={"key": "only"}).status_code == 400

    def test_delete(self, stub):
        client, assistant = stub
        client.post("/api/memory", json={"key": "gone", "value": "x"})
        body = client.delete("/api/memory/gone").get_json()
        assert body["deleted"] is True
        assert "gone" in assistant._memory.deleted

    def test_cancel_task(self, stub):
        client, assistant = stub
        body = client.delete("/api/tasks/t1").get_json()
        assert body["cancelled"] is True
        assert assistant._task_manager.cancelled == ["t1"]
