# crystal-beacon-lab

A small lab for studying **periodic telemetry (“beacon”) patterns** in a safe, non-offensive way.

The repo contains:
- a tiny **Crystal agent** that periodically POSTs a minimal JSON payload to a collector
- a tiny **Flask collector** that receives and echoes that payload

The emphasis is on **observability, reproducibility, and detection-thinking**—not exploitation.

## Why this exists
Periodic traffic isn’t inherently malicious; plenty of legitimate software “beacons.” But defenders still need to reason about:
- timing regularity / jitter
- payload stability vs drift
- what fields are actually useful for attribution
- how quickly a detection trips vs false positives

This lab gives you a clean signal you can measure, perturb, and build detections around.

## Safety / non-goals
- No exploitation
- No persistence
- No command-and-control
- No privilege escalation

It’s a telemetry toy designed for blue-team learning.

## Architecture
```
[crystal agent]  --(HTTP POST /ingest every N seconds)-->  [local flask collector]
```

## Data model (current)
The agent sends JSON shaped like:
- `agent_id` (random by default)
- `sent_at` (UTC timestamp)
- `host` (basic host metadata: user/hostname/os/cpu_count)

See `src/agent.cr` for the canonical schema.

## Quick start

### 1) Run the collector
```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
# listening on http://127.0.0.1:8080/ingest
```

### 2) Run the agent
You’ll need Crystal installed.

```bash
# from repo root
crystal run src/agent.cr -- \
  --url http://127.0.0.1:8080/ingest \
  --interval 15
```

You should see:
- the agent printing `sent_at=... status=200`
- the collector responding with `ok: true` and echoing the payload

## Experiments to try
- **Interval changes:** vary `--interval` and measure detection latency.
- **Jitter:** add random jitter to interval and observe how “beacon-like” it still appears.
- **Schema validation:** add strict JSON schema validation server-side.
- **Auth:** add a shared secret header to simulate authenticated telemetry.

## License
MIT
