"""
Tests for the shell_run deny-list — commands that confirmation must not be
able to authorise.
"""

import pytest

from tools.code_tools import _denied_pattern, shell_run


class TestDenyPattern:
    @pytest.mark.parametrize("command", [
        "format C: /fs:ntfs",
        "diskpart /s script.txt",
        "reg delete HKLM\\Software\\Foo /f",
        "vssadmin delete shadows /all",
        "Remove-Item -Recurse -Force C:\\Windows",
        "del /f /s /q C:\\",
    ])
    def test_dangerous_commands_are_denied(self, command):
        assert _denied_pattern(command) is not None

    @pytest.mark.parametrize("command", [
        "Get-Process",
        "dir C:\\Users",
        "echo hello",
        "Remove-Item .\\build -Recurse -Force",
        "git status",
    ])
    def test_ordinary_commands_are_allowed(self, command):
        assert _denied_pattern(command) is None

    def test_matching_is_case_insensitive(self):
        assert _denied_pattern("DISKPART") is not None

    def test_extra_whitespace_does_not_evade(self):
        assert _denied_pattern("reg    delete  HKLM\\Foo") is not None


class TestShellRunGuard:
    def test_denied_command_never_reaches_subprocess(self, monkeypatch):
        def fail(*args, **kwargs):
            raise AssertionError("subprocess.run was called for a denied command")

        monkeypatch.setattr("tools.code_tools.subprocess.run", fail)
        result = shell_run({"command": "diskpart"})
        assert result.success is False
        assert "blocked" in result.message.lower()

    def test_empty_command_is_rejected(self):
        assert shell_run({"command": ""}).success is False
