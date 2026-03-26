"""
API integration tests for the made. backend.

Uses FastAPI's TestClient (synchronous HTTPX-based client) for all tests.
Supabase and Redis are mocked via monkeypatch so no external services are needed.

Test groups:
- TestHealthCheck        — GET /health
- TestRootEndpoint       — GET /
- TestSignalRoutes       — GET /signals, GET /signals/{id}
- TestCalendarRoutes     — GET /calendar/today
- TestAuth               — POST /auth/login, GET /auth/me (unauthenticated)
- TestWebSocket          — Basic WebSocket connect/disconnect
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── App import with mocked dependencies ───────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Patch Redis so tests don't require a running Redis instance."""
    monkeypatch.setattr("api.redis_client._REDIS_AVAILABLE", False)
    monkeypatch.setattr("api.redis_client._redis", None)
    yield


@pytest.fixture(autouse=True)
def mock_supabase(monkeypatch):
    """Patch Supabase so tests don't require credentials."""
    monkeypatch.setattr("api.database._SUPABASE_AVAILABLE", False)
    monkeypatch.setattr("api.database._client", None)
    yield


@pytest.fixture
def client(mock_redis, mock_supabase):
    """Create a TestClient against the FastAPI app."""
    from api.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """
    Obtain a valid JWT token using dev credentials and return auth headers.
    """
    resp = client.post(
        "/auth/login",
        json={"email": "dev@made.app", "password": "made-dev-2026"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Health check ──────────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_returns_version(self, client):
        data = client.get("/health").json()
        assert "version" in data
        assert data["version"] == "1.0.0"


# ── Root endpoint ─────────────────────────────────────────────────────────────


class TestRootEndpoint:
    def test_root_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_returns_app_name(self, client):
        data = client.get("/").json()
        assert data["app"] == "made."

    def test_root_returns_version(self, client):
        data = client.get("/").json()
        assert data["version"] == "1.0.0"


# ── Signal routes ─────────────────────────────────────────────────────────────


class TestSignalRoutes:
    def test_get_signals_returns_200(self, client):
        resp = client.get("/signals")
        assert resp.status_code == 200

    def test_get_signals_returns_list(self, client):
        data = client.get("/signals").json()
        assert isinstance(data, list)

    def test_get_signals_contains_mock_data(self, client):
        """Dev mode should return at least one mock signal."""
        data = client.get("/signals").json()
        assert len(data) >= 1

    def test_get_signals_have_required_fields(self, client):
        data = client.get("/signals").json()
        if data:
            signal = data[0]
            required = {"signal_id", "pair", "direction", "entry_price", "stop_loss",
                        "confluence_score", "strength", "status"}
            for field in required:
                assert field in signal, f"Missing field: {field}"

    def test_get_signals_filter_by_pair(self, client):
        resp = client.get("/signals?pair=XAUUSD")
        assert resp.status_code == 200
        data = resp.json()
        for signal in data:
            assert signal["pair"] == "XAUUSD"

    def test_get_signals_filter_by_invalid_pair_returns_422(self, client):
        resp = client.get("/signals?pair=INVALID")
        assert resp.status_code == 422

    def test_get_signal_by_id_returns_404_for_unknown(self, client):
        resp = client.get("/signals/nonexistent-signal-id-00000")
        assert resp.status_code == 404

    def test_get_signal_by_id_returns_signal(self, client):
        # Get an existing signal ID from the list endpoint
        signals = client.get("/signals").json()
        if not signals:
            pytest.skip("No mock signals available")
        signal_id = signals[0]["signal_id"]
        resp = client.get(f"/signals/{signal_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["signal_id"] == signal_id

    def test_get_signal_history_requires_auth(self, client):
        """History endpoint returns empty list for unauthenticated requests."""
        resp = client.get("/signals/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_signal_history_with_auth(self, client, auth_headers):
        resp = client.get("/signals/history", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_shadow_signal_requires_internal_key(self, client):
        signals = client.get("/signals").json()
        if not signals:
            pytest.skip("No mock signals available")
        resp = client.post(
            "/signals/shadow",
            json=signals[0],
            headers={"X-Internal-Key": "wrong-key"},
        )
        assert resp.status_code == 403


# ── Calendar routes ───────────────────────────────────────────────────────────


class TestCalendarRoutes:
    def test_calendar_returns_200(self, client):
        resp = client.get("/calendar")
        assert resp.status_code == 200

    def test_calendar_returns_list(self, client):
        data = client.get("/calendar").json()
        assert isinstance(data, list)

    def test_calendar_today_returns_200(self, client):
        resp = client.get("/calendar/today")
        assert resp.status_code == 200

    def test_calendar_today_has_events_key(self, client):
        data = client.get("/calendar/today").json()
        assert "events" in data

    def test_calendar_today_has_date_key(self, client):
        data = client.get("/calendar/today").json()
        assert "date" in data

    def test_calendar_today_has_high_impact_count(self, client):
        data = client.get("/calendar/today").json()
        assert "high_impact_count" in data
        assert isinstance(data["high_impact_count"], int)

    def test_calendar_today_events_is_list(self, client):
        data = client.get("/calendar/today").json()
        assert isinstance(data["events"], list)

    def test_calendar_next_returns_200_or_null(self, client):
        resp = client.get("/calendar/next")
        assert resp.status_code == 200
        # Can be null (no upcoming events) or a dict (event found)
        body = resp.json()
        assert body is None or isinstance(body, dict)

    def test_calendar_filter_by_impact(self, client):
        resp = client.get("/calendar?impact=HIGH")
        assert resp.status_code == 200
        data = resp.json()
        for event in data:
            assert event["impact"] == "HIGH"

    def test_calendar_filter_by_invalid_impact_returns_422(self, client):
        resp = client.get("/calendar?impact=EXTREME")
        assert resp.status_code == 422


# ── Auth routes ───────────────────────────────────────────────────────────────


class TestAuth:
    def test_login_with_dev_credentials_returns_200(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "dev@made.app", "password": "made-dev-2026"},
        )
        assert resp.status_code == 200

    def test_login_returns_access_token(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "dev@made.app", "password": "made-dev-2026"},
        )
        data = resp.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 0

    def test_login_returns_refresh_token(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "dev@made.app", "password": "made-dev-2026"},
        )
        data = resp.json()
        assert "refresh_token" in data

    def test_login_returns_bearer_type(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "dev@made.app", "password": "made-dev-2026"},
        )
        assert resp.json()["token_type"] == "bearer"

    def test_login_with_wrong_password_returns_401(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "dev@made.app", "password": "wrong-password"},
        )
        assert resp.status_code == 401

    def test_login_with_unknown_email_returns_401(self, client):
        resp = client.post(
            "/auth/login",
            json={"email": "unknown@example.com", "password": "password123"},
        )
        assert resp.status_code == 401

    def test_login_with_no_credentials_returns_400(self, client):
        resp = client.post("/auth/login", json={})
        assert resp.status_code == 400

    def test_get_me_without_token_returns_401(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_get_me_with_valid_token_returns_200(self, client, auth_headers):
        resp = client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_me_returns_user_profile(self, client, auth_headers):
        data = client.get("/auth/me", headers=auth_headers).json()
        assert "user_id" in data
        assert "subscription_tier" in data
        assert "ui_mode" in data

    def test_get_me_with_invalid_token_returns_401(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    def test_token_refresh_works(self, client):
        login_resp = client.post(
            "/auth/login",
            json={"email": "dev@made.app", "password": "made-dev-2026"},
        )
        refresh_token = login_resp.json()["refresh_token"]
        resp = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_update_profile_requires_auth(self, client):
        resp = client.put("/auth/me", json={"ui_mode": "pro"})
        assert resp.status_code == 401

    def test_update_profile_trading_style(self, client, auth_headers):
        resp = client.put(
            "/auth/me",
            json={"trading_style": "swing_trading"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["trading_style"] == "swing_trading"

    def test_logout_requires_auth(self, client):
        resp = client.post("/auth/logout")
        assert resp.status_code == 401

    def test_logout_with_auth_returns_204(self, client, auth_headers):
        resp = client.post("/auth/logout", headers=auth_headers)
        assert resp.status_code == 204


# ── Journal routes ────────────────────────────────────────────────────────────


class TestJournalRoutes:
    def test_journal_requires_auth(self, client):
        resp = client.get("/journal")
        assert resp.status_code == 401

    def test_create_journal_entry(self, client, auth_headers):
        entry_data = {
            "pair": "XAUUSD",
            "direction": "BUY",
            "entry_price": 3045.50,
            "stop_loss": 3032.00,
            "tp1": 3059.00,
            "tp2": 3072.50,
            "tp3": 3091.00,
            "confluence_score": 0.78,
            "trading_style": "day_trading",
            "notes": "Test trade — London session OB setup",
        }
        resp = client.post("/journal", json=entry_data, headers=auth_headers)
        assert resp.status_code == 201

    def test_create_journal_entry_returns_id(self, client, auth_headers):
        entry_data = {
            "pair": "GBPJPY",
            "direction": "SELL",
            "entry_price": 195.42,
            "stop_loss": 195.82,
            "tp1": 195.02,
            "trading_style": "scalping",
        }
        data = client.post("/journal", json=entry_data, headers=auth_headers).json()
        assert "id" in data
        assert len(data["id"]) > 0

    def test_list_journal_entries(self, client, auth_headers):
        resp = client.get("/journal", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_journal_entry_not_found(self, client, auth_headers):
        resp = client.get("/journal/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_journal_entry(self, client, auth_headers):
        # Create then delete
        entry_data = {
            "pair": "XAUUSD",
            "direction": "BUY",
            "entry_price": 3050.0,
            "stop_loss": 3040.0,
            "tp1": 3060.0,
            "trading_style": "day_trading",
        }
        created = client.post("/journal", json=entry_data, headers=auth_headers).json()
        entry_id = created["id"]

        resp = client.delete(f"/journal/{entry_id}", headers=auth_headers)
        assert resp.status_code == 204

    def test_journal_stats_requires_auth(self, client):
        resp = client.get("/journal/stats")
        assert resp.status_code == 401

    def test_journal_stats_returns_summary(self, client, auth_headers):
        data = client.get("/journal/stats", headers=auth_headers).json()
        assert "total_trades" in data
        assert "win_rate" in data


# ── Analytics routes ──────────────────────────────────────────────────────────


class TestAnalyticsRoutes:
    def test_analytics_summary_requires_auth(self, client):
        resp = client.get("/analytics/summary")
        assert resp.status_code == 401

    def test_analytics_summary_returns_200(self, client, auth_headers):
        resp = client.get("/analytics/summary", headers=auth_headers)
        assert resp.status_code == 200

    def test_analytics_equity_curve_returns_list(self, client, auth_headers):
        data = client.get("/analytics/equity-curve", headers=auth_headers).json()
        assert isinstance(data, list)
        # Should have at least one point (starting equity)
        assert len(data) >= 1
        assert "equity" in data[0]
        assert "drawdown_pct" in data[0]

    def test_analytics_monthly_pnl_returns_dict(self, client, auth_headers):
        data = client.get("/analytics/monthly-pnl", headers=auth_headers).json()
        assert isinstance(data, dict)

    def test_analytics_by_session_returns_dict(self, client, auth_headers):
        data = client.get("/analytics/by-session", headers=auth_headers).json()
        assert isinstance(data, dict)


# ── WebSocket tests ───────────────────────────────────────────────────────────


class TestWebSocket:
    def test_websocket_connects(self, client):
        """WebSocket endpoint should accept connections."""
        with client.websocket_connect("/ws") as ws:
            # Connection established — server should send a PING or just stay open
            # We immediately close to avoid blocking
            pass

    def test_websocket_responds_to_ping(self, client):
        """Client PING message should receive a PONG response."""
        import json

        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            response = ws.receive_text()
            data = json.loads(response)
            assert data["type"] == "pong"

    def test_websocket_disconnect_is_graceful(self, client):
        """Disconnecting without error should not raise exceptions."""
        with client.websocket_connect("/ws") as ws:
            pass  # Disconnect on context manager exit — should be clean
