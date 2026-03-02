# crystal-beacon-lab

A small lab for studying **periodic telemetry (“beacon”) patterns** in a safe, non-offensive way.

The repo contains:
- a tiny **Crystal agent** that periodically POSTs a minimal JSON payload to a collector
- a **Flask collector** that stores events (SQLite) and exposes lightweight analysis endpoints

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

### Optional auth
Set `BEACON_KEY` on the collector to require the header `X-Beacon-Key`.
The agent will automatically send `X-Beacon-Key` if `BEACON_KEY` is set in its environment.

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

## License
MIT
