"""
Tests for Assistant behaviour that differs by input mode: special commands,
shutdown safety, and the confirmation channel.
"""

from unittest.mock import MagicMock

import pytest

from tests.test_listen import _make_assistant


class TestInputModeValidation:
    def test_known_modes_are_accepted(self):
        for mode in ("voice", "text", "api"):
            assert _make_assistant(mode).input_mode == mode

    def test_unknown_mode_is_rejected(self):
        with pytest.raises(ValueError):
            _make_assistant("telepathy")


class TestSpecialCommands:
    """
    Regression: these used to speak their answer and return True, so a web user
    heard the reply on the server's speakers and read "Special command handled."
    """

    def test_unrecognised_text_falls_through(self):
        assistant = _make_assistant("api")
        assert assistant._handle_special_commands("what's the weather") is None

    def test_clear_history_returns_its_own_text(self):
        assistant = _make_assistant("api")
        result = assistant._handle_special_commands("clear history")
        assert isinstance(result, str) and result.strip()
        assistant.brain.clear_history.assert_called_once()

    def test_special_command_does_not_speak_in_api_mode(self):
        assistant = _make_assistant("api")
        assistant._handle_special_commands("clear history")
        assistant.speaker.say.assert_not_called()

    def test_task_status_reports_the_summary(self):
        assistant = _make_assistant("api")
        assistant._task_manager.get_summary.return_value = "2 tasks running"
        assert assistant._handle_special_commands("what tasks are running") == "2 tasks running"

    def test_cancel_all_tasks(self):
        assistant = _make_assistant("api")
        assistant._handle_special_commands("cancel all tasks")
        assistant._task_manager.cancel_all.assert_called_once()

    def test_profile_with_no_facts(self):
        assistant = _make_assistant("api")
        assistant._memory.get_user_profile.return_value = {}
        assert "don't have any" in assistant._handle_special_commands("what do you know about me")

    def test_profile_with_facts(self):
        assistant = _make_assistant("api")
        assistant._memory.get_user_profile.return_value = {"favourite_colour": "blue"}
        result = assistant._handle_special_commands("what do you know about me")
        assert "favourite colour" in result and "blue" in result


class TestGoodbyeDoesNotKillTheServer:
    """
    Regression: "bye" over HTTP called shutdown(), which cancelled tasks and
    closed the memory DB that later requests still needed.
    """

    def test_api_mode_says_goodbye_without_shutting_down(self):
        assistant = _make_assistant("api")
        assistant.shutdown = MagicMock()
        result = assistant._handle_special_commands("bye")
        assert isinstance(result, str) and result.strip()
        assistant.shutdown.assert_not_called()

    def test_text_mode_still_shuts_down(self):
        assistant = _make_assistant("text")
        assistant.shutdown = MagicMock()
        assistant._handle_special_commands("quit")
        assistant.shutdown.assert_called_once()


class TestConfirmationChannel:
    def test_api_mode_denies_rather_than_guessing(self):
        """The server supplies its own per-request callback instead."""
        assistant = _make_assistant("api")
        assert assistant._interactive_confirm("shell_run", {"command": "dir"}) is False

    def test_voice_mode_accepts_a_spoken_yes(self):
        assistant = _make_assistant("voice")
        assistant.listener.listen.return_value = "yes go ahead"
        assert assistant._interactive_confirm("shell_run", {}) is True

    def test_voice_mode_treats_anything_else_as_no(self):
        assistant = _make_assistant("voice")
        assistant.listener.listen.return_value = "no don't"
        assert assistant._interactive_confirm("shell_run", {}) is False

    def test_voice_mode_treats_silence_as_no(self):
        assistant = _make_assistant("voice")
        assistant.listener.listen.return_value = None
        assert assistant._interactive_confirm("shell_run", {}) is False

    def test_text_mode_reads_stdin(self, monkeypatch):
        assistant = _make_assistant("text")
        monkeypatch.setattr("builtins.input", lambda *a: "yes")
        assert assistant._interactive_confirm("shell_run", {}) is True

    def test_text_mode_denies_on_eof(self, monkeypatch):
        assistant = _make_assistant("text")

        def raise_eof(*args):
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        assert assistant._interactive_confirm("shell_run", {}) is False


class TestProcessTextFull:
    def test_special_command_text_reaches_the_caller(self):
        assistant = _make_assistant("api")
        result = assistant.process_text_full("clear history")
        assert result["action"] == "built_in"
        assert "cleared" in result["response"].lower()

    def test_the_callers_confirm_callback_is_passed_to_the_registry(self):
        assistant = _make_assistant("api")
        assistant.brain.think.return_value = {
            "response": "ok", "action": "danger", "params": {"x": 1},
        }
        sentinel = lambda name, params: True

        assistant.process_text_full("do something", confirm_callback=sentinel)

        _, kwargs = assistant._tool_registry.execute.call_args
        assert kwargs["confirm_callback"] is sentinel

    def test_no_callback_means_none_is_forwarded(self):
        """ToolRegistry then denies CONFIRM tools, which is the safe default."""
        assistant = _make_assistant("api")
        assistant.brain.think.return_value = {
            "response": "ok", "action": "danger", "params": {},
        }

        assistant.process_text_full("do something")

        _, kwargs = assistant._tool_registry.execute.call_args
        assert kwargs["confirm_callback"] is None
