from datetime import datetime, timedelta, timezone

import pytest

from server import app as collector


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "DB_PATH", str(tmp_path / "beacons.sqlite"))
    monkeypatch.delenv("BEACON_KEY", raising=False)
    monkeypatch.setenv("REPLAY_WINDOW_SECONDS", "600")
    collector.app.config.update(TESTING=True)
    with collector.app.test_client() as test_client:
        yield test_client


def payload(**overrides):
    data = {
        "schema_version": 1,
        "agent_version": "0.2.0",
        "agent_id": "abcd1234",
        "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "nonce": "n1",
        "tags": {"env": "lab"},
        "user_agent": "test",
        "host": {"hostname": "h", "os": "linux", "cpu_count": 4, "user": "u"},
    }
    data.update(overrides)
    return data


def test_health_and_dashboard(client):
    assert client.get("/health").json["ok"] is True
    page = client.get("/")
    assert page.status_code == 200
    assert b"Beacon explorer" in page.data


def test_ingest_events_and_stats(client):
    assert client.post("/ingest", json=payload()).status_code == 200
    assert client.post("/ingest", json=payload(nonce="n2")).status_code == 200

    events = client.get("/events?agent_id=abcd1234&limit=1").json
    assert events["count"] == 1
    assert events["events"][0]["nonce"] == "n2"

    agent = client.get("/stats").json["agents"][0]
    assert agent["agent_id"] == "abcd1234"
    assert agent["events"] == 2
    assert agent["interarrival"]["count"] == 2
    assert agent["interarrival"]["median_s"] is not None
    assert agent["interarrival"]["cv"] is not None


@pytest.mark.parametrize("query", ["limit=abc", "limit=0", "limit=1001", "since=bad", "until=bad", "since=2026-03-02", "since=2026-03-03T00:00:00Z&until=2026-03-02T00:00:00Z"])
def test_events_rejects_invalid_filters(client, query):
    response = client.get(f"/events?{query}")
    assert response.status_code == 400
    assert response.json["ok"] is False


@pytest.mark.parametrize("body", [
    {"agent_id": ""},
    {"agent_id": "a", "schema_version": True},
    {"agent_id": "a", "schema_version": 2},
    {"agent_id": "a", "host": "not-an-object"},
])
def test_ingest_rejects_invalid_payload(client, body):
    response = client.post("/ingest", json=body)
    assert response.status_code == 400


def test_ingest_requires_json_and_limits_size(client):
    assert client.post("/ingest", data="hello").status_code == 415
    assert client.post("/ingest", data="{" + " " * 16_384, content_type="application/json").status_code == 413


def test_auth_optional(client, monkeypatch):
    monkeypatch.setenv("BEACON_KEY", "secret")
    assert client.post("/ingest", json=payload()).status_code == 401
    assert client.post("/ingest", json=payload(), headers={"X-Beacon-Key": "wrong"}).status_code == 401
    assert client.post("/ingest", json=payload(), headers={"X-Beacon-Key": "secret"}).status_code == 200


def test_stats_analyzes_recent_events(client):
    collector.init_db()
    with collector.db() as connection:
        connection.executemany(
            "INSERT INTO events (received_at, agent_id, payload_json) VALUES (?, ?, ?)",
            [
                ("2026-01-01T00:00:00Z", "a", "{}"),
                ("2026-01-01T00:00:10Z", "a", "{}"),
                ("2026-01-01T00:00:30Z", "a", "{}"),
            ],
        )
    summary = client.get("/stats").json["agents"][0]["interarrival"]
    assert summary["mean_s"] == 15
    assert summary["median_s"] == 15
    assert summary["min_s"] == 10
    assert summary["max_s"] == 20


def test_stats_samples_latest_2000_events(client):
    collector.init_db()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = [start] + [start + timedelta(hours=1, seconds=i) for i in range(2001)]
    with collector.db() as connection:
        connection.executemany(
            "INSERT INTO events (received_at, agent_id, payload_json) VALUES (?, ?, ?)",
            [(time.isoformat().replace("+00:00", "Z"), "a", "{}") for time in times],
        )
    agent = client.get("/stats").json["agents"][0]
    assert agent["events"] == 2002
    assert agent["interarrival"]["count"] == 2000
    assert agent["interarrival"]["mean_s"] == 1
