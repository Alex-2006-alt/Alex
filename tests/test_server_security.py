"""
Security hardening tests for the Flask API server:
- Token-based API authentication on all /api/* routes
- Constant-time token verification (hmac.compare_digest)
- Strict local-only CORS origin policy
- Secure token delivery into the web UI without leaking into logs or URLs
- Loopback bind enforcement and prohibition of debug mode / reloader
"""

import hmac
import pytest
import server


@pytest.fixture
def clean_client():
    """Client with no default credentials."""
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


class TestApiAuthentication:
    def test_unauthenticated_get_rejected(self, clean_client):
        res = clean_client.get("/api/status")
        assert res.status_code == 401
        assert res.get_json()["error"] == "Unauthorized"

    def test_unauthenticated_post_rejected(self, clean_client):
        res = clean_client.post("/api/chat", json={"message": "hello"})
        assert res.status_code == 401
        assert res.get_json()["error"] == "Unauthorized"

    def test_unauthenticated_action_rejected(self, clean_client):
        res = clean_client.post("/api/action", json={"action": "safe_probe"})
        assert res.status_code == 401
        assert res.get_json()["error"] == "Unauthorized"

    def test_invalid_bearer_token_rejected(self, clean_client):
        res = clean_client.get(
            "/api/status",
            headers={"Authorization": "Bearer invalid_secret_token_12345"}
        )
        assert res.status_code == 401
        assert res.get_json()["error"] == "Unauthorized"

    def test_invalid_x_alex_token_rejected(self, clean_client):
        res = clean_client.get(
            "/api/status",
            headers={"X-Alex-Token": "invalid_token_xyz"}
        )
        assert res.status_code == 401
        assert res.get_json()["error"] == "Unauthorized"

    def test_valid_bearer_token_accepted(self, clean_client):
        res = clean_client.get(
            "/api/status",
            headers={"Authorization": f"Bearer {server.API_TOKEN}"}
        )
        assert res.status_code == 200
        assert res.get_json()["status"] == "online"

    def test_valid_x_alex_token_accepted(self, clean_client):
        res = clean_client.get(
            "/api/status",
            headers={"X-Alex-Token": server.API_TOKEN}
        )
        assert res.status_code == 200
        assert res.get_json()["status"] == "online"

    def test_timing_attack_protection_uses_compare_digest(self, monkeypatch):
        called = []
        orig_compare = hmac.compare_digest

        def tracked_compare(a, b):
            called.append((a, b))
            return orig_compare(a, b)

        monkeypatch.setattr(hmac, "compare_digest", tracked_compare)
        server.app.config["TESTING"] = True
        with server.app.test_client() as c:
            c.get("/api/status", headers={"X-Alex-Token": server.API_TOKEN})

        assert len(called) >= 1
        assert any(call[1] == server.API_TOKEN for call in called)


class TestOriginAndCorsHardening:
    def test_unauthorized_external_origin_rejected(self, clean_client):
        res = clean_client.get(
            "/api/status",
            headers={
                "Origin": "https://malicious-site.example.com",
                "Authorization": f"Bearer {server.API_TOKEN}",
            }
        )
        assert res.status_code == 403
        assert "unauthorized origin" in res.get_json()["error"]

    def test_authorized_loopback_origin_accepted(self, clean_client):
        res = clean_client.get(
            "/api/status",
            headers={
                "Origin": "http://127.0.0.1:5000",
                "Authorization": f"Bearer {server.API_TOKEN}",
            }
        )
        assert res.status_code == 200

    def test_authorized_localhost_origin_accepted(self, clean_client):
        res = clean_client.get(
            "/api/status",
            headers={
                "Origin": "http://localhost:5000",
                "Authorization": f"Bearer {server.API_TOKEN}",
            }
        )
        assert res.status_code == 200


class TestWebUiTokenInjection:
    def test_index_injects_token_and_sets_no_store(self, clean_client):
        res = clean_client.get("/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert f'<meta name="alex-token" content="{server.API_TOKEN}">' in html
        assert "no-store" in res.headers.get("Cache-Control", "")


class TestServerBindAndDebugHardening:
    def test_server_main_overrides_non_loopback_host(self, monkeypatch):
        logged_errors = []
        monkeypatch.setattr(server.log, "error", lambda msg: logged_errors.append(msg))
        run_args = {}

        def mock_run(**kwargs):
            run_args.update(kwargs)

        monkeypatch.setattr(server.app, "run", mock_run)
        monkeypatch.setattr(
            "argparse.ArgumentParser.parse_args",
            lambda self: argparse.Namespace(host="0.0.0.0", port=5000, debug=True)
        )
        import argparse
        server.main()

        # Host must be forced to 127.0.0.1, debug must be False, use_reloader must be False
        assert run_args.get("host") == "127.0.0.1"
        assert run_args.get("debug") is False
        assert run_args.get("use_reloader") is False
        assert any("Refusing to bind" in err for err in logged_errors)
