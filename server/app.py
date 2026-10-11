from __future__ import annotations

import hmac
import json
import os
import re
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16_384

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "beacons.sqlite"))
REPLAY_WINDOW_SECONDS_DEFAULT = 600


SCHEMA_VERSION = 1


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_rfc3339(ts: str) -> Optional[datetime]:
    """Parse timestamps like 2026-03-02T01:23:45Z."""
    if not isinstance(ts, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", ts
    ):
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
    if not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 128:
        return ValidationResult(False, "agent_id must be a nonempty string of at most 128 characters")

    sv = data.get("schema_version", SCHEMA_VERSION)
    if type(sv) is not int or sv != SCHEMA_VERSION:
        return ValidationResult(False, f"schema_version must be {SCHEMA_VERSION}")

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
    if not hmac.compare_digest(provided, beacon_key):
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
    auth_err = auth_check()
    if auth_err:
        return jsonify({"ok": False, "error": auth_err}), 401

    if not request.is_json:
        return jsonify({"ok": False, "error": "Content-Type must be application/json"}), 415
    if request.content_length is not None and request.content_length > 16_384:
        return jsonify({"ok": False, "error": "payload exceeds 16 KiB"}), 413
    data = request.get_json(silent=True)
    vr = validate_payload(data)
    if not vr.ok:
        return jsonify({"ok": False, "error": vr.error}), 400

    replay_err = replay_check(data.get("sent_at"))
    if replay_err:
        return jsonify({"ok": False, "error": replay_err}), 400

    init_db()

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
    try:
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    if not 1 <= limit <= 1000:
        return jsonify({"ok": False, "error": "limit must be between 1 and 1000"}), 400

    since_raw = request.args.get("since")
    until_raw = request.args.get("until")
    since = parse_rfc3339(since_raw) if since_raw else None
    until = parse_rfc3339(until_raw) if until_raw else None
    if (since_raw and not since) or (until_raw and not until):
        return jsonify({"ok": False, "error": "since and until must be RFC3339 timestamps"}), 400
    if since and until and since > until:
        return jsonify({"ok": False, "error": "since must be before until"}), 400

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
        return {"count": len(times), "min_s": None, "mean_s": None, "median_s": None, "max_s": None, "stdev_s": None, "cv": None}

    # sort ascending
    times = sorted(times)
    diffs = [(times[i] - times[i - 1]).total_seconds() for i in range(1, len(times))]
    mean = statistics.mean(diffs)
    stdev = statistics.pstdev(diffs)
    return {
        "count": len(times),
        "min_s": min(diffs),
        "mean_s": mean,
        "median_s": statistics.median(diffs),
        "max_s": max(diffs),
        "stdev_s": stdev,
        "cv": stdev / mean if mean else None,
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
                "SELECT received_at FROM events WHERE agent_id = ? ORDER BY id DESC LIMIT 2000", (agent_id,)
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


@app.get("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    init_db()
    app.run(host=HOST, port=PORT, debug=False)
