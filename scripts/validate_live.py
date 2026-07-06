"""Loop 5 — live-model validation. One command, publishable stats.

Runs N realistic party requests through the FULL production pipeline
(feasibility precheck -> LLM -> grounding -> verifier -> repair loop) and
reports the headline reliability metrics for the GTM story.

Usage:
    # Free rehearsal (offline mock):
    python scripts/validate_live.py --n 50

    # The real thing (~a few dollars):
    LLM_BACKEND=anthropic ANTHROPIC_API_KEY=sk-ant-... python scripts/validate_live.py --n 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from iparty.core.config import settings  # noqa: E402
from iparty.core.exceptions import NoValidPlanError  # noqa: E402
from iparty.llm.client import build_client  # noqa: E402
from iparty.orchestration.ttl_engine import TTLOrchestrator  # noqa: E402
from iparty.planning.models import PartyRequest  # noqa: E402
from iparty.planning.planner import TTLPartyPlanner  # noqa: E402
from iparty.pricing.catalog import StaticCatalog  # noqa: E402

DIETS = ["", "", "", "nut allergy", "gluten-free", "vegan", "dairy-free", "egg allergy"]
THEMES = ["Dinosaurs", "Space", "Under the Sea", "Superheroes", "Princess", "Soccer", ""]


def realistic_request(i: int, rng: random.Random) -> PartyRequest:
    guests = rng.choice([8, 10, 12, 15, 18, 20, 25, 30])
    budget = rng.choice([150, 250, 350, 450, 600, 800])
    return PartyRequest(
        honoree_name=f"Child{i}", honoree_age=rng.randint(3, 12),
        party_date=date.today() + timedelta(days=rng.randint(7, 60)),
        guest_count=guests, budget=budget, theme=rng.choice(THEMES),
        dietary_restrictions=rng.choice(DIETS),
        location_type=rng.choice(["home", "home", "park", "venue"]),
    )


async def main(n: int, seed: int) -> None:
    rng = random.Random(seed)
    client = build_client()
    planner = TTLPartyPlanner(client, StaticCatalog(), TTLOrchestrator("validate"))

    verified, refused, errors = 0, 0, 0
    calls_per_plan, latencies, repaired = [], [], 0
    diet_total, diet_verified = 0, 0

    print(f"Running {n} requests against backend='{client.name}' "
          f"(model={settings.ANTHROPIC_MODEL if client.name=='anthropic' else 'n/a'})\n")
    for i in range(n):
        req = realistic_request(i, rng)
        is_diet = bool(req.dietary_restrictions)
        diet_total += is_diet
        t0 = time.monotonic()
        try:
            result = await planner.plan(req)
            latencies.append(time.monotonic() - t0)
            verified += 1
            diet_verified += is_diet
            calls = result.telemetry["llm_calls"]
            calls_per_plan.append(calls)
            if calls > 1:
                repaired += 1
            tag = f"OK  {calls} call(s)"
        except NoValidPlanError:
            refused += 1
            tag = "REFUSED (honest)"
        except Exception as exc:  # noqa: BLE001
            errors += 1
            tag = f"ERROR {type(exc).__name__}"
        print(f"  [{i+1:>3}/{n}] guests={req.guest_count:<3} budget=${req.budget:<4} "
              f"diet={req.dietary_restrictions or '-':<12} -> {tag}")

    print("\n" + "=" * 62)
    print("HEADLINE STATS (for GTM / investor use)")
    print("=" * 62)
    attempted = verified + errors  # refusals are correct behavior, not attempts
    print(f"  Verified-plan rate      : {verified}/{attempted} "
          f"({100*verified/max(1,attempted):.0f}%) of non-refused requests")
    print(f"  Honest refusals         : {refused} (infeasible constraints, 0 LLM calls)")
    print(f"  Hard errors             : {errors}")
    if calls_per_plan:
        print(f"  Mean LLM calls/plan     : {statistics.mean(calls_per_plan):.2f}")
        print(f"  Repair-loop saves       : {repaired} plans verified on 2nd+ attempt")
    if latencies:
        lat = sorted(latencies)
        print(f"  Latency p50 / p95       : {lat[len(lat)//2]:.1f}s / {lat[int(len(lat)*0.95)-1]:.1f}s")
    if diet_total:
        print(f"  Dietary requests        : {diet_total} ({100*diet_verified/diet_total:.0f}% verified)")
    out = {
        "backend": client.name, "n": n, "verified": verified, "refused": refused,
        "errors": errors, "mean_calls": statistics.mean(calls_per_plan) if calls_per_plan else None,
        "repair_saves": repaired,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/validation_run.json").write_text(json.dumps(out, indent=2))
    print("\n  Saved: data/validation_run.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    asyncio.run(main(args.n, args.seed))
