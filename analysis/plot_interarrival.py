"""Plot inter-arrival timing for a given agent_id.

This script is intentionally lightweight: it pulls recent events from the collector
and plots a histogram of inter-arrival deltas.

Usage:
  python analysis/plot_interarrival.py --base-url http://127.0.0.1:8080 --agent-id abcd1234 --limit 500

Outputs:
  out/interarrival_<agent_id>.png
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime

import requests
import matplotlib.pyplot as plt


def parse_rfc3339(ts: str) -> datetime:
    # expected like 2026-03-02T01:23:45Z
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8080", help="Collector base URL")
    ap.add_argument("--agent-id", required=True, help="agent_id to analyze")
    ap.add_argument("--limit", type=int, default=500, help="max events to fetch")
    ap.add_argument("--out-dir", default="out", help="output directory")
    ap.add_argument(
        "--beacon-key",
        default=os.environ.get("BEACON_KEY", ""),
        help="optional BEACON_KEY (also read from env)",
    )
    args = ap.parse_args()

    headers = {}
    if args.beacon_key:
        headers["X-Beacon-Key"] = args.beacon_key

    url = f"{args.base_url.rstrip('/')}/events"
    r = requests.get(url, params={"agent_id": args.agent_id, "limit": args.limit}, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    events = data.get("events", [])

    # /events returns newest-first. Sort by received_at ascending for deltas.
    times = sorted(parse_rfc3339(e["received_at"]) for e in events if e.get("received_at"))

    if len(times) < 2:
        raise SystemExit("Not enough events to compute inter-arrival deltas.")

    deltas = [(times[i] - times[i - 1]).total_seconds() for i in range(1, len(times))]

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, f"interarrival_{args.agent_id}.png")

    plt.figure(figsize=(10, 5))
    plt.hist(deltas, bins=30)
    plt.title(f"Inter-arrival deltas (s) for agent_id={args.agent_id}")
    plt.xlabel("seconds")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)

    print(out_path)


if __name__ == "__main__":
    main()
