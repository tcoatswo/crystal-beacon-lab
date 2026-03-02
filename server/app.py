from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request

app = Flask(__name__)

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "beacons.sqlite"))
REPLAY_WINDOW_SECONDS_DEFAULT = 600


SCHEMA_VERSION = 1


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_rfc3339(ts: str) -> Optional[datetime]:
    """Parse timestamps like 2026-03-02T01:23:45Z."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with db() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              received_at TEXT NOT NULL,
              agent_id TEXT NOT NULL,
              sent_at TEXT,
              nonce TEXT,
              schema_version INTEGER,
              payload_json TEXT NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_events_agent_id ON events(agent_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_events_received_at ON events(received_at)")


@dataclass
class ValidationResult:
    ok: bool
    error: Optional[str] = None


def validate_payload(data: Dict[str, Any]) -> ValidationResult:
    if not isinstance(data, dict):
        return ValidationResult(False, "payload must be a JSON object")

    agent_id = data.get("agent_id")
    if not agent_id or not isinstance(agent_id, str):
        return ValidationResult(False, "agent_id is required")

    sv = data.get("schema_version", SCHEMA_VERSION)
    if not isinstance(sv, int):
        return ValidationResult(False, "schema_version must be an integer")

    # Basic shape checks (lab-grade; intentionally light)
    host = data.get("host")
    if host is not None and not isinstance(host, dict):
        return ValidationResult(False, "host must be an object")

    sent_at = data.get("sent_at")
    if sent_at is not None and parse_rfc3339(sent_at) is None:
        return ValidationResult(False, "sent_at must be RFC3339 (e.g. 2026-03-02T01:23:45Z)")

    nonce = data.get("nonce")
    if nonce is not None and not isinstance(nonce, str):
        return ValidationResult(False, "nonce must be a string")

    return ValidationResult(True)


def auth_check() -> Optional[str]:
    """Return error string if auth fails; else None.

    Note: we read env vars at request-time so tests and local runs can toggle
    BEACON_KEY without relying on module reload behavior.
    """
    beacon_key = os.environ.get("BEACON_KEY")
    if not beacon_key:
        return None
    provided = request.headers.get("X-Beacon-Key")
    if not provided:
        return "missing X-Beacon-Key"
    if provided != beacon_key:
        return "invalid X-Beacon-Key"
    return None


def replay_check(sent_at: Optional[str]) -> Optional[str]:
    if not sent_at:
        return None
    dt = parse_rfc3339(sent_at)
    if not dt:
        return "invalid sent_at"

    replay_window = int(os.environ.get("REPLAY_WINDOW_SECONDS", str(REPLAY_WINDOW_SECONDS_DEFAULT)))
    age = abs((utcnow() - dt).total_seconds())
    if age > replay_window:
        return f"sent_at outside replay window ({replay_window}s)"
    return None


@app.get("/health")
def health():
    return jsonify({"ok": True, "schema_version": SCHEMA_VERSION, "db_path": DB_PATH}), 200


@app.post("/ingest")
def ingest():
    init_db()

    auth_err = auth_check()
    if auth_err:
        return jsonify({"ok": False, "error": auth_err}), 401

    data = request.get_json(force=True, silent=True) or {}
    vr = validate_payload(data)
    if not vr.ok:
        return jsonify({"ok": False, "error": vr.error}), 400

    replay_err = replay_check(data.get("sent_at"))
    if replay_err:
        return jsonify({"ok": False, "error": replay_err}), 400

    received_at = utcnow().isoformat().replace("+00:00", "Z")
    agent_id = data.get("agent_id")
    sent_at = data.get("sent_at")
    nonce = data.get("nonce")
    schema_version = data.get("schema_version", SCHEMA_VERSION)

    # store as canonical JSON
    payload_json = json.dumps(data, separators=(",", ":"), sort_keys=True)

    with db() as con:
        con.execute(
            """
            INSERT INTO events (received_at, agent_id, sent_at, nonce, schema_version, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (received_at, agent_id, sent_at, nonce, schema_version, payload_json),
        )

    # lightweight log line
    print(f"received_at={received_at} agent_id={agent_id} nonce={nonce}")

    return jsonify({"ok": True, "received_at": received_at}), 200


@app.get("/events")
def events():
    init_db()

    agent_id = request.args.get("agent_id")
    limit = int(request.args.get("limit", "100"))
    limit = max(1, min(limit, 1000))

    since = parse_rfc3339(request.args.get("since", "") or "")
    until = parse_rfc3339(request.args.get("until", "") or "")

    clauses = []
    params: List[Any] = []

    if agent_id:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    if since:
        clauses.append("received_at >= ?")
        params.append(since.isoformat().replace("+00:00", "Z"))
    if until:
        clauses.append("received_at <= ?")
        params.append(until.isoformat().replace("+00:00", "Z"))

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    q = f"SELECT id, received_at, agent_id, sent_at, nonce, schema_version, payload_json FROM events {where} ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with db() as con:
        rows = con.execute(q, params).fetchall()

    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "received_at": r["received_at"],
                "agent_id": r["agent_id"],
                "sent_at": r["sent_at"],
                "nonce": r["nonce"],
                "schema_version": r["schema_version"],
                "payload": json.loads(r["payload_json"]),
            }
        )

    return jsonify({"ok": True, "count": len(out), "events": out}), 200


def interarrival_stats(times: List[datetime]) -> Dict[str, Any]:
    if len(times) < 2:
        return {"count": len(times), "min_s": None, "mean_s": None, "max_s": None}

    # sort ascending
    times = sorted(times)
    diffs = [(times[i] - times[i - 1]).total_seconds() for i in range(1, len(times))]
    return {
        "count": len(times),
        "min_s": min(diffs),
        "mean_s": sum(diffs) / len(diffs),
        "max_s": max(diffs),
    }


@app.get("/stats")
def stats():
    init_db()

    with db() as con:
        agents = con.execute(
            "SELECT agent_id, COUNT(*) AS n, MAX(received_at) AS last_received_at FROM events GROUP BY agent_id ORDER BY n DESC"
        ).fetchall()

    by_agent = []
    for a in agents:
        agent_id = a["agent_id"]
        with db() as con:
            rows = con.execute(
                "SELECT received_at FROM events WHERE agent_id = ? ORDER BY id ASC LIMIT 2000", (agent_id,)
            ).fetchall()

        times = []
        for r in rows:
            dt = parse_rfc3339(r["received_at"])
            if dt:
                times.append(dt)

        by_agent.append(
            {
                "agent_id": agent_id,
                "events": int(a["n"]),
                "last_received_at": a["last_received_at"],
                "interarrival": interarrival_stats(times),
            }
        )

    return jsonify({"ok": True, "schema_version": SCHEMA_VERSION, "agents": by_agent}), 200


# Simple dashboard (no JS frameworks) for quick lab checks
@app.get("/")
def index():
    return (
        """
<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1' />
    <title>crystal-beacon-lab</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; max-width: 900px; margin: 40px auto; padding: 0 16px; }
      code, pre { background: #f6f8fa; padding: 2px 6px; border-radius: 6px; }
      pre { padding: 12px; overflow-x: auto; }
      .muted { color: #57606a; }
    </style>
  </head>
  <body>
    <h1>crystal-beacon-lab</h1>
    <p class='muted'>Local telemetry collector. Endpoints: <code>/health</code>, <code>/ingest</code>, <code>/events</code>, <code>/stats</code>.</p>
    <h2>Quick check</h2>
    <pre id='out'>Loading...</pre>
    <script>
      fetch('/stats').then(r => r.json()).then(j => {
        document.getElementById('out').textContent = JSON.stringify(j, null, 2);
      }).catch(e => {
        document.getElementById('out').textContent = String(e);
      });
    </script>
  </body>
</html>
""".strip(),
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


if __name__ == "__main__":
    init_db()
    app.run(host=HOST, port=PORT, debug=True)
