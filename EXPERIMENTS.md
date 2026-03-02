# Experiments

This repo is intentionally small; the point is to enable quick measurement loops.

## 1) Timing regularity vs jitter
- Baseline: fixed interval (e.g., 15s)
- Variant: interval + uniform jitter (e.g., ±3s)

Questions:
- How much jitter is required before a simple periodicity detector fails?
- What does this imply for tuning beacon-detection thresholds?

## 2) Payload stability
- Baseline: stable fields only
- Variant: introduce a rotating field (nonce) vs a drifting field (counter)

Questions:
- Which fields actually matter for correlating events to an agent?
- Which are likely to create false positives in enterprise telemetry?

## 3) Collector hardening
- Add schema validation
- Add auth (shared secret)
- Add rate limiting

Question:
- What does “safe telemetry” look like when you treat it like a real service?
