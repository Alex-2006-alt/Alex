"""
Tests for ALEX ToolRegistry — registration, result normalisation, and the
confirmation gate that guards CONFIRM-level tools.
"""

import pytest

from core.tool_registry import (
    ToolRegistry,
    ToolResult,
    ToolSpec,
    SafetyLevel,
)


def _spec(name, fn, safety=SafetyLevel.SAFE, **kw):
    return ToolSpec(
        name=name,
        description=kw.pop("description", f"test tool {name}"),
        fn=fn,
        parameters=kw.pop("parameters", {}),
        safety=safety,
        category=kw.pop("category", "testing"),
    )


@pytest.fixture
def registry():
    """A registry isolated from the global singleton."""
    return ToolRegistry()


class TestRegistration:
    def test_register_and_get(self, registry):
        registry.register(_spec("noop", lambda p: "ok"))
        assert registry.get("noop") is not None
        assert len(registry) == 1

    def test_unknown_tool_reports_available_tools(self, registry):
        registry.register(_spec("noop", lambda p: "ok"))
        result = registry.execute("does_not_exist", {})
        assert result.success is False
        assert "noop" in result.error

    def test_alias_resolves_to_canonical_name(self, registry):
        registry.register(_spec("web_search", lambda p: "searched"))
        result = registry.execute("search_web", {})
        assert result.success is True
        assert result.message == "searched"

    def test_list_by_category(self, registry):
        registry.register(_spec("a", lambda p: "", category="files"))
        registry.register(_spec("b", lambda p: "", category="files"))
        registry.register(_spec("c", lambda p: "", category="web"))
        assert registry.list_by_category() == {"files": ["a", "b"], "web": ["c"]}


class TestResultNormalisation:
    def test_string_result_becomes_successful_toolresult(self, registry):
        registry.register(_spec("s", lambda p: "hello"))
        result = registry.execute("s", {})
        assert result.success is True
        assert result.message == "hello"

    def test_dict_result_is_preserved_as_data(self, registry):
        registry.register(_spec("d", lambda p: {"k": "v"}))
        result = registry.execute("d", {})
        assert result.success is True
        assert result.data == {"k": "v"}

    def test_toolresult_passes_through_untouched(self, registry):
        original = ToolResult(success=False, error="nope")
        registry.register(_spec("t", lambda p: original))
        assert registry.execute("t", {}) is original

    def test_exception_becomes_failed_toolresult(self, registry):
        def boom(params):
            raise RuntimeError("kaboom")

        registry.register(_spec("boom", boom))
        result = registry.execute("boom", {})
        assert result.success is False
        assert "kaboom" in result.error

    def test_params_are_forwarded(self, registry):
        registry.register(_spec("echo", lambda p: p.get("msg", "")))
        assert registry.execute("echo", {"msg": "hi"}).message == "hi"


class TestConfirmationGate:
    """
    A CONFIRM-level tool must never run without an explicit approval.
    Regression guard: execute() used to treat a missing callback as consent,
    so the web API and every agentic plan step ran destructive tools silently.
    """

    def setup_method(self):
        self.calls = []

    def _dangerous(self, params):
        self.calls.append(params)
        return "executed"

    def _registry_with_dangerous(self):
        reg = ToolRegistry()
        reg.register(_spec("danger", self._dangerous, safety=SafetyLevel.CONFIRM))
        return reg

    def test_missing_callback_denies_and_does_not_execute(self):
        reg = self._registry_with_dangerous()
        result = reg.execute("danger", {"x": 1})
        assert result.success is False
        assert self.calls == [], "tool ran without confirmation"

    def test_callback_returning_false_denies(self):
        reg = self._registry_with_dangerous()
        result = reg.execute("danger", {}, confirm_callback=lambda n, p: False)
        assert result.success is False
        assert "cancelled" in result.message.lower()
        assert self.calls == []

    def test_callback_returning_true_executes(self):
        reg = self._registry_with_dangerous()
        result = reg.execute("danger", {}, confirm_callback=lambda n, p: True)
        assert result.success is True
        assert len(self.calls) == 1

    def test_auto_approve_is_an_explicit_opt_in(self):
        reg = self._registry_with_dangerous()
        result = reg.execute("danger", {}, confirm_callback=ToolRegistry.AUTO_APPROVE)
        assert result.success is True
        assert len(self.calls) == 1

    def test_callback_receives_tool_name_and_params(self):
        reg = self._registry_with_dangerous()
        seen = {}

        def spy(name, params):
            seen["name"] = name
            seen["params"] = params
            return True

        reg.execute("danger", {"cmd": "dir"}, confirm_callback=spy)
        assert seen == {"name": "danger", "params": {"cmd": "dir"}}

    def test_safe_tools_run_without_a_callback(self):
        reg = ToolRegistry()
        reg.register(_spec("safe", lambda p: "fine", safety=SafetyLevel.SAFE))
        assert reg.execute("safe", {}).success is True

    def test_warn_tools_run_without_a_callback(self):
        reg = ToolRegistry()
        reg.register(_spec("warn", lambda p: "fine", safety=SafetyLevel.WARN))
        assert reg.execute("warn", {}).success is True

    def test_real_dangerous_tools_are_confirm_level(self):
        """The five tools the gate is there to protect."""
        import tools  # noqa: F401 — registers everything

        reg = ToolRegistry.get_instance()
        for name in ("shell_run", "code_run", "file_delete", "process_kill", "system_power"):
            spec = reg.get(name)
            assert spec is not None, f"{name} is not registered"
            assert spec.safety == SafetyLevel.CONFIRM, f"{name} is not CONFIRM-level"
