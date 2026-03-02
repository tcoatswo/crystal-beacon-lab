import os
import json
import tempfile

import pytest


@pytest.fixture()
def client(monkeypatch):
    # Import app after setting env vars
    import importlib

    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()

    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("REPLAY_WINDOW_SECONDS", "999999")

    mod = importlib.import_module("server.app")
    mod.init_db()

    mod.app.config.update({"TESTING": True})
    with mod.app.test_client() as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json["ok"] is True


def test_ingest_and_stats(client):
    payload = {
        "schema_version": 1,
        "agent_version": "0.2.0",
        "agent_id": "abcd1234",
        "sent_at": "2026-03-02T01:23:45Z",
        "nonce": "n1",
        "tags": {"env": "lab"},
        "user_agent": "test",
        "host": {"hostname": "h", "os": "linux", "cpu_count": 4, "user": "u"},
    }

    r = client.post("/ingest", json=payload)
    assert r.status_code == 200

    r2 = client.get("/stats")
    assert r2.status_code == 200
    assert any(a["agent_id"] == "abcd1234" for a in r2.json["agents"])


def test_auth_optional(monkeypatch):
    # When BEACON_KEY is set, request must include it
    import importlib
    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()

    monkeypatch.setenv("DB_PATH", tmp.name)
    monkeypatch.setenv("BEACON_KEY", "secret")
    monkeypatch.setenv("REPLAY_WINDOW_SECONDS", "999999")

    mod = importlib.import_module("server.app")
    mod.init_db()

    mod.app.config.update({"TESTING": True})
    c = mod.app.test_client()

    payload = {"agent_id": "a", "sent_at": "2026-03-02T01:23:45Z"}

    r = c.post("/ingest", json=payload)
    assert r.status_code == 401

    r2 = c.post("/ingest", json=payload, headers={"X-Beacon-Key": "secret"})
    assert r2.status_code == 200
