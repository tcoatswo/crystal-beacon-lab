# crystal-beacon-lab

A small lab for studying **periodic telemetry (“beacon”) patterns** in a safe, non-offensive way.

The repo contains:
- a tiny **Crystal agent** that periodically POSTs a minimal JSON payload to a collector
- a **Flask collector** that stores events (SQLite) and exposes lightweight analysis endpoints
- a browser dashboard for exploring agent activity and inter-arrival timing

The emphasis is on **observability, reproducibility, and detection-thinking**—not exploitation.

## Safety / non-goals
- No exploitation
- No persistence
- No command-and-control
- No privilege escalation

It’s a telemetry toy designed for blue-team learning.

## Architecture
```
[crystal agent]  --(HTTP POST /ingest every N seconds)-->  [flask collector]  ->  [SQLite]
```

## Quick start (recommended: Docker Compose)

```bash
docker compose up --build
# collector at http://127.0.0.1:8080/
```

Compose binds the collector to your local loopback interface. Open the dashboard to see agent counts, recent events, and a timing chart. It refreshes every 15 seconds.

Then run the agent locally (requires Crystal):

```bash
crystal run src/agent.cr -- \
  --url http://127.0.0.1:8080/ingest \
  --interval 15 \
  --jitter 3 \
  --tag env=lab
```

## Collector endpoints
- `GET /` — tiny dashboard (loads `/stats`)
- `GET /health`
- `POST /ingest` — store an event
- `GET /events?agent_id=...&limit=...&since=...&until=...`
- `GET /stats` — per-agent counts + inter-arrival summaries

`/stats` reports minimum, mean, median, maximum, standard deviation, and coefficient of variation (CV) for the most recent 2,000 received events per agent. CV is standard deviation divided by mean; higher values indicate less regular timing. The dashboard chart shows the most recent 50 inter-arrival intervals from the last 100 events.

`/events` accepts `limit` from 1 to 1,000 and optional RFC3339 `since` and `until` filters. Invalid values return HTTP 400.

### Optional auth
Set `BEACON_KEY` on the collector to require the header `X-Beacon-Key`.
The agent will automatically send `X-Beacon-Key` if `BEACON_KEY` is set in its environment.
This optional key protects ingestion. Keep the collector bound to loopback because the dashboard and read endpoints expose lab event data.

The collector accepts JSON payloads up to 16 KiB and schema version 1. It rejects unsupported content types and malformed filters with clear errors.

## Data model (current)
The agent sends JSON with:
- `schema_version`
- `agent_version`
- `agent_id`
- `sent_at` (UTC)
- `nonce`
- `tags` (key/value)
- `user_agent`
- `host` (basic host metadata)

See `src/agent.cr` for the canonical schema.

## Experiments
See `EXPERIMENTS.md`.

## Analysis (plot inter-arrival timing)
If you want a quick visualization of how jitter changes timing distributions:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r analysis/requirements.txt
python analysis/plot_interarrival.py --base-url http://127.0.0.1:8080 --agent-id <agent_id> --limit 500
```

This writes a PNG under `out/`.

## Development checks

```bash
python3 -m venv .venv
.venv/bin/pip install -r server/requirements-dev.txt
.venv/bin/python -m pytest -q
crystal build src/agent.cr -o /tmp/crystal-beacon-agent
```

CI runs collector tests on Python 3.12 and 3.13 and compiles the Crystal agent. The runtime container installs Flask only; pytest stays in the development requirements.

## License
MIT
