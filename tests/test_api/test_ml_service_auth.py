"""Auth coverage for the ml_service service-token middleware (gap #8).

When ``SERVICE_AUTH_TOKEN`` is set, every request except the /health probe must
present a matching ``X-Service-Token`` header; when unset, the middleware is a
no-op (local dev / tests). The middleware reads the module global
``_SERVICE_AUTH_TOKEN`` at request time, so tests monkeypatch that global rather
than the process environment.

A non-existent route is used as the probe: the middleware runs before routing,
so a correct token yields 404 (auth passed, no route) while a bad/absent token
yields 401 (blocked first) — exercising the gate without invoking any heavy
handler.
"""

import pytest

pytest.importorskip("fastapi")

TOKEN = "test-service-token"
PROBE = "/ml/__no_such_route__"


def _client():
    from fastapi.testclient import TestClient

    from ml_service.main import app

    return TestClient(app)


class TestServiceAuthMiddleware:
    def test_enforced_missing_header_is_401(self, monkeypatch):
        monkeypatch.setattr("ml_service.main._SERVICE_AUTH_TOKEN", TOKEN)
        r = _client().post(PROBE, json={})
        assert r.status_code == 401
        assert r.json()["error"] == "unauthorized"

    def test_enforced_wrong_header_is_401(self, monkeypatch):
        monkeypatch.setattr("ml_service.main._SERVICE_AUTH_TOKEN", TOKEN)
        r = _client().post(PROBE, json={}, headers={"X-Service-Token": "wrong"})
        assert r.status_code == 401

    def test_enforced_correct_header_passes_auth(self, monkeypatch):
        """Correct token clears the gate; 404 (not 401) proves it reached routing."""
        monkeypatch.setattr("ml_service.main._SERVICE_AUTH_TOKEN", TOKEN)
        r = _client().post(PROBE, json={}, headers={"X-Service-Token": TOKEN})
        assert r.status_code == 404

    def test_health_is_exempt_even_when_enforced(self, monkeypatch):
        monkeypatch.setattr("ml_service.main._SERVICE_AUTH_TOKEN", TOKEN)
        r = _client().get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_disabled_when_token_unset_is_bypass(self, monkeypatch):
        """Empty token => no enforcement: the probe reaches routing (404), no 401."""
        monkeypatch.setattr("ml_service.main._SERVICE_AUTH_TOKEN", "")
        r = _client().post(PROBE, json={})
        assert r.status_code == 404
