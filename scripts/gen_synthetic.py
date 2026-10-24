"""Generate SIMULATED LabFlow pipeline + past-event outcomes (fixed seed, reproducible)."""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos.config import DATA  # noqa: E402

rng = random.Random(42)
accounts = list(csv.DictReader(open(DATA / "icp_accounts.csv")))
seeds = list(csv.DictReader(open(DATA / "event_seeds.csv")))
out = DATA / "synthetic"
out.mkdir(exist_ok=True)

stages = ["discovery", "evaluation", "proposal", "negotiation"]
with open(out / "pipeline.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["opp_id", "account_id", "stage", "amount_usd", "created_at", "simulated"])
    n = 0
    for a in accounts:
        if rng.random() < 0.45:
            n += 1
            base = {"1": 250_000, "2": 120_000, "3": 60_000}[a["tier"]]
            w.writerow([f"O{n:03d}", a["account_id"], rng.choice(stages),
                        int(base * rng.uniform(0.5, 1.8) // 1000 * 1000),
                        f"2026-{rng.randint(4, 10):02d}-{rng.randint(1, 28):02d}", "true"])

with open(out / "past_event_outcomes.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["series", "year", "spend_usd", "meetings", "opps_created", "pipeline_usd", "simulated"])
    for s in seeds:
        for year in (2024, 2025, 2026):
            if rng.random() < 0.6:
                spend = rng.randint(15, 60) * 1000
                meetings = rng.randint(3, 25)
                opps = rng.randint(0, max(1, meetings // 4))
                w.writerow([s["series"], year, spend, meetings, opps, opps * rng.randint(40, 200) * 1000, "true"])

print("Wrote", out / "pipeline.csv", "and", out / "past_event_outcomes.csv")
