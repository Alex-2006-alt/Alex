"""
Tests for ALEX listen adapters on the Assistant class.

These tests use heavy mocking to avoid loading real audio/LLM dependencies.
"""

from unittest.mock import patch, MagicMock


def _make_assistant(input_mode="text"):
    """
    Build an Assistant instance with all heavy subsystems mocked out
    so tests run instantly without audio devices, Whisper models, or API keys.
    """
    with patch("core.assistant.Listener"), \
         patch("core.assistant.Speaker"), \
         patch("core.assistant.Brain") as MockBrain, \
         patch("core.assistant.WakeWordDetector"):

        # Stub out the Brain instance methods that __init__ calls
        brain_inst = MockBrain.return_value
        brain_inst.set_tool_registry = MagicMock()
        brain_inst.set_memory = MagicMock()
        brain_inst.set_task_manager = MagicMock()
        brain_inst.get_current_plan.return_value = None

        # Patch the init helpers so they set safe defaults instead of
        # trying to import real modules (tools, memory, etc.)
        def _fake_init_tool_registry(self):
            self._tool_registry = MagicMock()
            self._tool_registry.__len__ = MagicMock(return_value=0)

        def _fake_init_memory(self):
            self._memory = MagicMock()
            self._memory.stats.return_value = {"facts": 0, "tasks": 0}

        def _fake_init_task_manager(self):
            self._task_manager = MagicMock()
            self._monitor = None

        with patch.object(
            __import__("core.assistant", fromlist=["Assistant"]).Assistant,
            "_init_tool_registry",
            _fake_init_tool_registry,
        ), patch.object(
            __import__("core.assistant", fromlist=["Assistant"]).Assistant,
            "_init_memory",
            _fake_init_memory,
        ), patch.object(
            __import__("core.assistant", fromlist=["Assistant"]).Assistant,
            "_init_task_manager",
            _fake_init_task_manager,
        ):
            from core.assistant import Assistant
            assistant = Assistant(use_wake_word=False, input_mode=input_mode)

    return assistant



class TestListenText:
    """Tests for listen_text()."""

    def test_returns_stripped_text(self):
        assistant = _make_assistant(input_mode="text")
        with patch("builtins.input", return_value="  hello world  "):
            result = assistant.listen_text()
        assert result == "hello world"

    def test_returns_none_on_empty_input(self):
        assistant = _make_assistant(input_mode="text")
        with patch("builtins.input", return_value=""):
            result = assistant.listen_text()
        assert result is None

    def test_returns_none_on_whitespace(self):
        assistant = _make_assistant(input_mode="text")
        with patch("builtins.input", return_value="   "):
            result = assistant.listen_text()
        assert result is None

    def test_returns_none_on_eof(self):
        assistant = _make_assistant(input_mode="text")
        with patch("builtins.input", side_effect=EOFError):
            result = assistant.listen_text()
        assert result is None

    def test_returns_none_on_keyboard_interrupt(self):
        assistant = _make_assistant(input_mode="text")
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = assistant.listen_text()
        assert result is None


class TestListenVoice:
    """Tests for listen_voice()."""

    def test_delegates_to_listener(self):
        assistant = _make_assistant(input_mode="voice")
        assistant.listener.listen.return_value = "hello from mic"
        result = assistant.listen_voice()
        assert result == "hello from mic"
        assistant.listener.listen.assert_called_once()

    def test_returns_none_when_no_speech(self):
        assistant = _make_assistant(input_mode="voice")
        assistant.listener.listen.return_value = None
        result = assistant.listen_voice()
        assert result is None


class TestListenRouting:
    """Tests for the listen() router."""

    def test_text_mode_routes_to_listen_text(self):
        assistant = _make_assistant(input_mode="text")
        with patch.object(assistant, "listen_text", return_value="typed") as mock_lt:
            result = assistant.listen()
        mock_lt.assert_called_once()
        assert result == "typed"

    def test_voice_mode_routes_to_listen_voice(self):
        assistant = _make_assistant(input_mode="voice")
        with patch.object(assistant, "listen_voice", return_value="spoken") as mock_lv:
            result = assistant.listen()
        mock_lv.assert_called_once()
        assert result == "spoken"
