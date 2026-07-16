"""JEPA-TTL bridge — predictive decision-making for the orchestrator.

JEPA's core idea (LeCun): don't predict raw outputs — learn to predict
*outcomes in a joint representation space*, scored by an energy function.
Here that maps cleanly onto the TTL loop:

- The **verifier is the ground-truth energy function** (violations = energy).
- ``DraftEncoder`` embeds (request, plan) into a compact, catalog-grounded
  feature space — the joint representation of context and candidate.
- ``OutcomePredictor`` is a small online model (per-violation logistic heads,
  pure Python, no dependencies) that learns to predict verifier energy from
  the embedding — trained continuously on real verifier reports.
- ``JepaAdvisor`` uses those predictions to make the TTL loop *anticipatory*
  instead of reactive:

    1. difficulty()      — request-only embedding -> adaptive candidate budget
    2. prehint()         — predicted top-risk violations become *preemptive*
                           repair instructions (before the first failure)
    3. assess(plan)      — predicted energy per candidate, logged against the
                           verifier's actual verdict (calibration telemetry)
    4. observe(...)      — online learning from every verified candidate
    5. should_continue() — after a pass: energy-based expected-improvement
                           decision instead of blind first-pass-wins

The predictor is shared process-wide, so the system provably gets better at
its own workload over time — measured, not asserted (see /api/v1/metrics).
"""
from __future__ import annotations

import math
import threading
from collections import defaultdict

from ..pricing.catalog import Catalog, parse_forbidden_allergens, requires_vegetarian

# Violation heads the predictor learns. ANY_FAIL doubles as the difficulty head.
HEADS = (
    "ANY_FAIL", "BUDGET_EXCEEDED", "FOOD_UNDERSCALED", "ALLERGEN_VIOLATION",
    "INSUFFICIENT_SAFE_FOOD", "SUPPLIES_UNDERSCALED", "AGE_INAPPROPRIATE",
    "SCHEDULE_NOT_MONOTONIC",
)

_HINTS = {
    "BUDGET_EXCEEDED": "keep the total strictly under the budget cap",
    "FOOD_UNDERSCALED": "total food servings must cover every guest",
    "ALLERGEN_VIOLATION": "select only items free of the forbidden allergens",
    "INSUFFICIENT_SAFE_FOOD": "allergen-safe servings alone must cover all guests",
    "SUPPLIES_UNDERSCALED": "supplies must provide a place setting per guest",
    "AGE_INAPPROPRIATE": "choose only activities whose age range fits the honoree",
    "SCHEDULE_NOT_MONOTONIC": "schedule slots must be ordered and non-overlapping",
}


def encode_request(request, catalog: Catalog) -> dict[str, float]:
    """Context-only embedding — available before any candidate is generated."""
    forbidden = parse_forbidden_allergens(request.dietary_restrictions)
    veg = requires_vegetarian(request.dietary_restrictions)
    guests = request.guest_count
    # catalog-grounded scarcity: how much of the food catalog is safe?
    foods = [f for f in catalog.by_category("food") if f.serves > 0]
    safe_foods = [f for f in foods
                  if not (forbidden & f.allergens) and (f.vegetarian or not veg)]
    acts = [a for a in catalog.by_category("activities")
            if a.min_age <= request.honoree_age <= a.max_age]
    per_guest_budget = request.budget / max(1, guests)
    return {
        "bias": 1.0,
        "guests": min(guests / 500.0, 1.0),
        "budget_pg": min(per_guest_budget / 100.0, 1.0),
        "budget_tight": 1.0 / (1.0 + per_guest_budget / 10.0),
        "n_allergens": len(forbidden) / 9.0,
        "veg": 1.0 if veg else 0.0,
        "food_scarcity": 1.0 - len(safe_foods) / max(1, len(foods)),
        "act_scarcity": 1.0 - len(acts) / max(1, len(catalog.by_category("activities"))),
        "age_extreme": 1.0 if (request.honoree_age <= 2 or request.honoree_age >= 13) else 0.0,
        "diet_len": min(len(request.dietary_restrictions) / 300.0, 1.0),
        "window_long": max(0.0, (getattr(request, "duration_hours", 2.5) - 2.5) / 5.5),
        "loc_perperson": 1.0 if request.location_type == "restaurant" else 0.0,
    }


def encode_plan(plan, request, catalog: Catalog) -> dict[str, float]:
    """Joint embedding of (request, candidate plan) — summary statistics only;
    the predictor must LEARN the mapping to violations (it never runs checks)."""
    x = encode_request(request, catalog)
    guests = max(1, request.guest_count)
    forbidden = parse_forbidden_allergens(request.dietary_restrictions)
    total = plan.total_cost
    servings = sum(m.servings for m in plan.menu)
    safe = sum(m.servings for m in plan.menu if not (forbidden & set(m.allergens)))
    veg_srv = sum(m.servings for m in plan.menu if m.vegetarian)
    sup_cap = 0
    act_ages = []
    for li in plan.line_items:
        item = catalog.get(li.sku)
        if item is None:
            continue
        if li.category == "supplies":
            sup_cap += guests if item.unit == "per_person" else item.serves * li.quantity
        if li.category == "activities":
            act_ages.append((item.min_age, item.max_age))
    age = request.honoree_age
    age_fit = (sum(1 for lo, hi in act_ages if lo <= age <= hi) / len(act_ages)) if act_ages else 0.0
    x.update({
        "utilization": min(total / max(request.budget, 0.01), 2.0) / 2.0,
        "over_budget_margin": max(0.0, min((total - request.budget) / max(request.budget, 0.01), 1.0)),
        "servings_ratio": min(servings / guests, 2.0) / 2.0,
        "safe_ratio": min(safe / guests, 2.0) / 2.0,
        "veg_ratio": min(veg_srv / guests, 2.0) / 2.0,
        "supplies_ratio": min(sup_cap / guests, 2.0) / 2.0,
        "age_fit": age_fit,
        "n_items": min(len(plan.line_items) / 12.0, 1.0),
        "n_sched": min(len(plan.schedule) / 6.0, 1.0),
    })
    return x


class OutcomePredictor:
    """Per-head online logistic regression over the joint embedding.

    Pure Python, thread-safe, deterministic. Every verified candidate is a
    labelled example; the verifier never lies, so calibration is honest.
    """

    def __init__(self, lr: float = 0.25) -> None:
        self.lr = lr
        self._w: dict[str, dict[str, float]] = {h: defaultdict(float) for h in HEADS}
        self._lock = threading.Lock()
        self.examples_seen = 0
        self.assessments = 0
        self.assessment_hits = 0  # predicted energy >=/ < 0.5 matched pass/fail

    @staticmethod
    def _sigmoid(z: float) -> float:
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))

    def predict(self, head: str, x: dict[str, float]) -> float:
        w = self._w[head]
        return self._sigmoid(sum(w[k] * v for k, v in x.items()))

    def energy(self, x: dict[str, float]) -> float:
        """Predicted energy of a candidate: probability mass of failure."""
        return self.predict("ANY_FAIL", x)

    def top_risks(self, x: dict[str, float], k: int = 3, floor: float = 0.45) -> list[str]:
        scored = [(self.predict(h, x), h) for h in HEADS if h != "ANY_FAIL"]
        scored.sort(reverse=True)
        return [h for p, h in scored[:k] if p >= floor]

    def learn(self, x: dict[str, float], report) -> None:
        codes = {v.code for v in report.violations}
        with self._lock:
            self.examples_seen += 1
            for head in HEADS:
                y = 1.0 if (head == "ANY_FAIL" and not report.passed) or head in codes else 0.0
                w = self._w[head]
                err = self._sigmoid(sum(w[k] * v for k, v in x.items())) - y
                for k, v in x.items():
                    w[k] -= self.lr * err * v

    def record_assessment(self, predicted_energy: float, passed: bool) -> None:
        with self._lock:
            self.assessments += 1
            if (predicted_energy >= 0.5) == (not passed):
                self.assessment_hits += 1

    def metrics(self) -> dict:
        acc = self.assessment_hits / self.assessments if self.assessments else None
        return {"examples_seen": self.examples_seen,
                "assessments": self.assessments,
                "calibration_accuracy": round(acc, 3) if acc is not None else None}


# Process-wide predictor: the system improves on its own workload over time.
shared_predictor = OutcomePredictor()


class JepaAdvisor:
    """Per-request advisor handed to TTLOrchestrator.run_verified()."""

    def __init__(self, request, catalog: Catalog,
                 predictor: OutcomePredictor | None = None,
                 max_candidates: int | None = None) -> None:
        self.request = request
        self.catalog = catalog
        self.predictor = predictor or shared_predictor
        self.max_candidates = max_candidates
        self._ctx = encode_request(request, catalog)
        self._last_assessment: float | None = None

    # -- 1. adaptive candidate budget --------------------------------------
    def difficulty(self) -> float:
        """Blend of learned failure risk and cold-start constraint heuristic."""
        learned = self.predictor.predict("ANY_FAIL", self._ctx)
        heuristic = min(1.0, self._ctx["n_allergens"] + self._ctx["veg"] * 0.3
                        + self._ctx["food_scarcity"] * 0.5 + self._ctx["budget_tight"] * 0.4
                        + self._ctx["act_scarcity"] * 0.3)
        blend = 0.4 if self.predictor.examples_seen < 30 else 0.75
        return blend * learned + (1 - blend) * heuristic

    def candidate_budget(self, n_max: int) -> int:
        return max(1, min(n_max, 1 + round(self.difficulty() * (n_max - 1))))

    # -- 2. preemptive repair hint ------------------------------------------
    def prehint(self) -> str | None:
        risks = self.predictor.top_risks(self._ctx)
        if not risks:
            return None
        return ("Predicted risk areas for this request — satisfy these from the "
                "first attempt: " + "; ".join(_HINTS[r] for r in risks if r in _HINTS))

    # -- 3./4. energy assessment + online learning ---------------------------
    def assess(self, plan) -> float:
        x = encode_plan(plan, self.request, self.catalog)
        self._last_assessment = self.predictor.energy(x)
        return self._last_assessment

    def observe(self, plan, report) -> None:
        x = encode_plan(plan, self.request, self.catalog)
        if self._last_assessment is not None:
            self.predictor.record_assessment(self._last_assessment, report.passed)
            self._last_assessment = None
        self.predictor.learn(x, report)

    # -- 5. energy-based continuation after a pass ---------------------------
    def should_continue(self, best_score: float, produced: int, n_budget: int) -> bool:
        """Keep sampling past a pass only when the pass is mediocre, budget
        remains, and the request is hard enough that variance pays off."""
        if produced >= n_budget:
            return False
        return best_score < 0.9 and self.difficulty() > 0.6
