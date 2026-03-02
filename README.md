# crystal-beacon-lab

## For grad-school reviewers (what this demonstrates)
**crystal-beacon-lab** is an **engineering-focused lab**: it demonstrates how to design and implement a safe **agent → collector telemetry pipeline** (client instrumentation, structured payloads, and a minimal ingest service).

**Primary outcomes:**
- Systems-oriented implementation in **Crystal** (CLI design, configuration, builds)
- **Structured telemetry** (JSON payload design suitable for downstream analysis)
- Reproducible local development loop (optional collector server)

**Safety boundary:** This repo intentionally includes **no persistence** and **no remote tasking/command execution**.

**Related (defender/policy capstone) repo:** For detections (Sigma/osquery), benign validation, and policy artifacts derived from “beacon-style” behaviors, see **beacon-to-blue**: https://github.com/tcoatswo/beacon-to-blue

---

A **safe, educational** Crystal project that demonstrates how to build a small “agent → collector” pipeline:

- a Crystal CLI that periodically sends **telemetry** (host metadata) to an HTTP endpoint
- an optional tiny local collector server for development
- reproducible outputs and clear boundaries (no persistence, no remote command execution)

This repo is meant to showcase:
- systems programming basics in Crystal
- clean CLI design + configuration
- structured JSON payloads
- defensive / blue-team relevant engineering

## Non-goals (important)
This project intentionally does **not** implement:
- persistence mechanisms
- covert communications / “evasion”
- memory-only execution / shell tasking / arbitrary code execution

## Quickstart

### 1) Build
```bash
crystal build src/agent.cr -o crystal-beacon
```

### 2) Run a local collector
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r server/requirements.txt
python server/app.py
```

### 3) Run the agent
```bash
./crystal-beacon --url http://127.0.0.1:8080/ingest --interval 15
```

## Example payload
```json
{
  "agent_id": "a1b2c3d4",
  "sent_at": "2026-03-01T16:00:00Z",
  "host": {
    "user": "tyler",
    "hostname": "devbox",
    "os": "linux",
    "cpu_count": 8
  }
}
```

## License
MIT
