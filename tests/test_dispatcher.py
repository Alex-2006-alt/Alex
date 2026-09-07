"""
Tests for ALEX CommandDispatcher.
"""

import datetime
from unittest.mock import patch

from core.command_dispatcher import CommandDispatcher


class TestDispatcherBuiltins:
    """Tests for built-in command handlers."""

    def setup_method(self):
        self.dispatcher = CommandDispatcher(register_builtins=True)

    def test_say_time_returns_current_date(self):
        result = self.dispatcher.dispatch("say_time")
        assert result is not None
        today = datetime.datetime.now()
        # Result should contain the current day name
        assert today.strftime("%A") in result

    def test_say_time_alias_time(self):
        result = self.dispatcher.dispatch("time")
        assert result is not None
        assert ":" in result  # contains a time component

    def test_say_time_alias_what_time(self):
        result = self.dispatcher.dispatch("what time")
        assert result is not None

    def test_open_url_missing_url(self):
        result = self.dispatcher.dispatch("open_url")
        assert result is not None
        assert "provide a URL" in result.lower() or "example" in result.lower()

    @patch("webbrowser.open")
    def test_open_url_with_url(self, mock_open):
        result = self.dispatcher.dispatch("open_url https://example.com")
        assert result is not None
        assert "example.com" in result
        mock_open.assert_called_once_with("https://example.com")

    @patch("webbrowser.open")
    def test_open_url_adds_https(self, mock_open):
        result = self.dispatcher.dispatch("open_url google.com")
        assert result is not None
        mock_open.assert_called_once_with("https://google.com")

    def test_unrecognized_command_returns_none(self):
        result = self.dispatcher.dispatch("tell me a joke")
        assert result is None

    def test_empty_text_returns_none(self):
        result = self.dispatcher.dispatch("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = self.dispatcher.dispatch("   ")
        assert result is None


class TestDispatcherCustomHandlers:
    """Tests for custom handler registration."""

    def test_register_and_dispatch_custom_handler(self):
        dispatcher = CommandDispatcher(register_builtins=False)
        dispatcher.register("greet", lambda args: f"Hello, {args}!")
        result = dispatcher.dispatch("greet World")
        assert result == "Hello, World!"

    def test_custom_alias_dispatch(self):
        dispatcher = CommandDispatcher(register_builtins=False)
        dispatcher.register("greet", lambda args: "Hi!", aliases=["hello", "hey"])
        assert dispatcher.dispatch("hello") == "Hi!"
        assert dispatcher.dispatch("hey") == "Hi!"

    def test_list_commands(self):
        dispatcher = CommandDispatcher(register_builtins=False)
        dispatcher.register("alpha", lambda _: "a")
        dispatcher.register("beta", lambda _: "b")
        assert dispatcher.list_commands() == ["alpha", "beta"]

    def test_handler_receives_args_text(self):
        dispatcher = CommandDispatcher(register_builtins=False)
        received = {}

        def capture(args):
            received["args"] = args
            return "ok"

        dispatcher.register("echo", capture)
        dispatcher.dispatch("echo foo bar baz")
        assert received["args"] == "foo bar baz"

    def test_handler_error_returns_error_string(self):
        dispatcher = CommandDispatcher(register_builtins=False)
        dispatcher.register("boom", lambda _: (_ for _ in ()).throw(ValueError("kaboom")))
        result = dispatcher.dispatch("boom")
        assert result is not None
        assert "error" in result.lower() or "kaboom" in result.lower()
