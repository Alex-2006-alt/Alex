"""
Tests for the web confirmation flow.

A request that hits a CONFIRM-level tool parks a pending confirmation and
blocks; the browser polls for it and answers. These tests drive that handshake
directly, without constructing a real Assistant.
"""

import threading
import time

import pytest

import server


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c
    # Never leak a parked confirmation into the next test
    with server._pending_lock:
        for entry in server._pending.values():
            entry["event"].set()
        server._pending.clear()


def _ask(tool="shell_run", params=None, into=None):
    """Run _request_confirmation on a background thread, recording its answer."""
    result = into if into is not None else {}

    def run():
        result["answer"] = server._request_confirmation(tool, params or {"command": "dir"})

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, result


def _wait_for_pending(client, timeout=3.0):
    """Poll /api/confirmations until something shows up."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get("/api/confirmations").get_json()
        if body["count"]:
            return body["pending"][0]
        time.sleep(0.02)
    raise AssertionError("no confirmation appeared")


class TestConfirmationHandshake:
    def test_pending_confirmation_is_listed(self, client):
        thread, result = _ask(tool="file_delete", params={"path": "C:/tmp/x"})
        item = _wait_for_pending(client)

        assert item["tool"] == "file_delete"
        assert item["params"] == {"path": "C:/tmp/x"}
        assert item["expires_in"] > 0

        client.post("/api/confirm", json={"confirmation_id": item["id"], "approved": False})
        thread.join(timeout=3)

    def test_approval_unblocks_the_request_with_true(self, client):
        thread, result = _ask()
        item = _wait_for_pending(client)

        resp = client.post("/api/confirm", json={"confirmation_id": item["id"], "approved": True})
        assert resp.get_json()["approved"] is True

        thread.join(timeout=3)
        assert result["answer"] is True

    def test_denial_unblocks_the_request_with_false(self, client):
        thread, result = _ask()
        item = _wait_for_pending(client)

        client.post("/api/confirm", json={"confirmation_id": item["id"], "approved": False})
        thread.join(timeout=3)
        assert result["answer"] is False

    def test_answering_clears_it_from_the_pending_list(self, client):
        thread, _ = _ask()
        item = _wait_for_pending(client)
        client.post("/api/confirm", json={"confirmation_id": item["id"], "approved": True})
        thread.join(timeout=3)

        assert client.get("/api/confirmations").get_json()["count"] == 0

    def test_timeout_denies(self, client, monkeypatch):
        monkeypatch.setattr(server.config, "CONFIRMATION_TIMEOUT", 1)
        thread, result = _ask()
        thread.join(timeout=5)
        assert result["answer"] is False, "an unanswered prompt must not approve"

    def test_two_confirmations_are_tracked_independently(self, client):
        t1, r1 = _ask(tool="shell_run")
        t2, r2 = _ask(tool="system_power")

        deadline = time.time() + 3
        while time.time() < deadline:
            pending = client.get("/api/confirmations").get_json()["pending"]
            if len(pending) == 2:
                break
            time.sleep(0.02)
        else:
            raise AssertionError("expected two pending confirmations")

        by_tool = {p["tool"]: p["id"] for p in pending}
        client.post("/api/confirm", json={"confirmation_id": by_tool["shell_run"], "approved": True})
        client.post("/api/confirm", json={"confirmation_id": by_tool["system_power"], "approved": False})
        t1.join(timeout=3)
        t2.join(timeout=3)

        assert r1["answer"] is True
        assert r2["answer"] is False


class TestConfirmEndpointValidation:
    def test_missing_id_is_a_400(self, client):
        assert client.post("/api/confirm", json={"approved": True}).status_code == 400

    def test_unknown_id_is_a_404(self, client):
        resp = client.post("/api/confirm", json={"confirmation_id": "nope", "approved": True})
        assert resp.status_code == 404

    def test_empty_list_when_nothing_pending(self, client):
        body = client.get("/api/confirmations").get_json()
        assert body == {"pending": [], "count": 0}
