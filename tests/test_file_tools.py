"""
Tests for the file tool allow-list.

Regression guard: _is_allowed_path existed but was never called, so
config.ALLOWED_FILE_PATHS restricted nothing and file_write / file_delete /
file_move could touch any path on the machine.
"""

from pathlib import Path

import pytest

import config
from tools.file_tools import (
    _is_allowed_path,
    file_write,
    file_delete,
    file_mkdir,
    file_move,
    file_copy,
    file_read,
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Restrict the allow-list to a temp directory for the duration of a test."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    monkeypatch.setattr(config, "ENFORCE_FILE_ALLOWLIST", True)
    monkeypatch.setattr(config, "ALLOWED_FILE_PATHS", [str(allowed)])
    return allowed, outside


class TestIsAllowedPath:
    def test_path_inside_an_allowed_root(self, sandbox):
        allowed, _ = sandbox
        assert _is_allowed_path(allowed / "notes.txt") is True

    def test_nested_path_inside_an_allowed_root(self, sandbox):
        allowed, _ = sandbox
        assert _is_allowed_path(allowed / "a" / "b" / "c.txt") is True

    def test_path_outside_is_rejected(self, sandbox):
        _, outside = sandbox
        assert _is_allowed_path(outside / "notes.txt") is False

    def test_traversal_out_of_an_allowed_root_is_rejected(self, sandbox):
        allowed, _ = sandbox
        assert _is_allowed_path(allowed / ".." / "outside" / "x.txt") is False

    def test_sibling_prefix_is_not_treated_as_inside(self, tmp_path, monkeypatch):
        """'/allowed' must not match '/allowed_evil'."""
        monkeypatch.setattr(config, "ENFORCE_FILE_ALLOWLIST", True)
        monkeypatch.setattr(config, "ALLOWED_FILE_PATHS", [str(tmp_path / "allowed")])
        (tmp_path / "allowed").mkdir()
        assert _is_allowed_path(tmp_path / "allowed_evil" / "x.txt") is False

    def test_empty_allow_list_permits_everything(self, monkeypatch):
        monkeypatch.setattr(config, "ALLOWED_FILE_PATHS", [])
        assert _is_allowed_path("C:/Windows/System32/drivers/etc/hosts") is True

    def test_enforcement_can_be_switched_off(self, sandbox, monkeypatch):
        _, outside = sandbox
        monkeypatch.setattr(config, "ENFORCE_FILE_ALLOWLIST", False)
        assert _is_allowed_path(outside / "x.txt") is True


class TestMutatingToolsRespectTheAllowList:
    def test_write_inside_succeeds(self, sandbox):
        allowed, _ = sandbox
        result = file_write({"path": str(allowed / "ok.txt"), "content": "hi"})
        assert result.success is True
        assert (allowed / "ok.txt").read_text() == "hi"

    def test_write_outside_is_refused_and_creates_nothing(self, sandbox):
        _, outside = sandbox
        target = outside / "nope.txt"
        result = file_write({"path": str(target), "content": "hi"})
        assert result.success is False
        assert not target.exists()

    def test_delete_outside_is_refused_and_leaves_the_file(self, sandbox):
        _, outside = sandbox
        victim = outside / "keep.txt"
        victim.write_text("important")
        result = file_delete({"path": str(victim)})
        assert result.success is False
        assert victim.exists()

    def test_delete_inside_succeeds(self, sandbox):
        allowed, _ = sandbox
        victim = allowed / "gone.txt"
        victim.write_text("x")
        assert file_delete({"path": str(victim)}).success is True
        assert not victim.exists()

    def test_mkdir_outside_is_refused(self, sandbox):
        _, outside = sandbox
        target = outside / "newdir"
        assert file_mkdir({"path": str(target)}).success is False
        assert not target.exists()

    def test_move_out_of_the_allow_list_is_refused(self, sandbox):
        allowed, outside = sandbox
        src = allowed / "a.txt"
        src.write_text("x")
        result = file_move({"source": str(src), "destination": str(outside / "a.txt")})
        assert result.success is False
        assert src.exists(), "source was moved despite the refusal"

    def test_move_into_the_allow_list_is_refused_when_source_is_outside(self, sandbox):
        allowed, outside = sandbox
        src = outside / "b.txt"
        src.write_text("x")
        result = file_move({"source": str(src), "destination": str(allowed / "b.txt")})
        assert result.success is False
        assert src.exists()

    def test_move_within_the_allow_list_succeeds(self, sandbox):
        allowed, _ = sandbox
        src = allowed / "c.txt"
        src.write_text("x")
        dst = allowed / "sub" / "c.txt"
        assert file_move({"source": str(src), "destination": str(dst)}).success is True
        assert dst.exists()

    def test_copy_to_outside_is_refused(self, sandbox):
        allowed, outside = sandbox
        src = allowed / "d.txt"
        src.write_text("x")
        dst = outside / "d.txt"
        assert file_copy({"source": str(src), "destination": str(dst)}).success is False
        assert not dst.exists()

    def test_copy_from_outside_into_the_allow_list_is_permitted(self, sandbox):
        """Reading is unrestricted, so pulling a file in is fine."""
        allowed, outside = sandbox
        src = outside / "e.txt"
        src.write_text("x")
        dst = allowed / "e.txt"
        assert file_copy({"source": str(src), "destination": str(dst)}).success is True
        assert dst.read_text() == "x"


class TestReadingIsUnrestricted:
    def test_read_outside_the_allow_list_still_works(self, sandbox):
        _, outside = sandbox
        f = outside / "readme.txt"
        f.write_text("visible")
        result = file_read({"path": str(f)})
        assert result.success is True
        assert "visible" in result.message

    def test_missing_file_reports_cleanly(self, sandbox):
        allowed, _ = sandbox
        assert file_read({"path": str(allowed / "ghost.txt")}).success is False

    def test_empty_path_is_rejected(self):
        assert file_read({"path": ""}).success is False
        assert file_write({"path": "", "content": "x"}).success is False
