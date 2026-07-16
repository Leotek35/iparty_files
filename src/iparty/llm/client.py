"""LLM client protocol + Anthropic and Mock backends.

Backends return a PlanDraft (catalog SELECTIONS, never prices). The Mock is
offline and deterministic so the repo runs and CI passes with zero secrets.
"""
from __future__ import annotations

import json
import random
import re
from typing import Protocol

from ..core.config import settings
from ..core.exceptions import MalformedPlanError
from ..core.logging import get_logger
from ..pricing.catalog import Catalog
from ..planning.feasibility import cheapest_compliant_draft
from ..pricing.catalog import parse_forbidden_allergens, requires_vegetarian
from ..planning.models import PartyRequest, PlanDraft, Selection
from ..planning.prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger("llm")


class LLMClient(Protocol):
    name: str

    async def generate_draft(
        self, request: PartyRequest, catalog: Catalog,
        temperature: float = 0.5, feedback: "str | None" = None,
    ) -> PlanDraft: ...


def _parse_draft_json(text: str) -> PlanDraft:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise MalformedPlanError("no JSON object found in model output")
    try:
        return PlanDraft.model_validate(json.loads(match.group(0)))
    except Exception as exc:  # noqa: BLE001
        raise MalformedPlanError(f"could not parse draft: {exc}") from exc


class AnthropicClient:
    name = "anthropic"

    def __init__(self) -> None:
        from anthropic import AsyncAnthropic

        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set but LLM_BACKEND=anthropic")
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL

    async def generate_draft(self, request, catalog, temperature=0.5, feedback=None) -> PlanDraft:
        user = build_user_prompt(request, catalog)
        if feedback:
            user += ("\n\nIMPORTANT — your previous selection failed verification:\n"
                     + feedback + "\nReturn a corrected JSON selection.")
        resp = await self._client.messages.create(
            model=self._model, max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            temperature=min(1.0, temperature), system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return _parse_draft_json(text)


class MockClient:
    """Offline planner. Starts from the cheapest compliant draft, then sometimes
    upgrades items (and occasionally overshoots budget) to exercise the verifier
    and the best-of-N / circuit-breaker path."""

    name = "mock"

    def __init__(self, seed: int = 0, flaw_rate: float = 0.35) -> None:
        self._seed = seed
        self._flaw_rate = flaw_rate
        self._call = 0

    async def generate_draft(self, request, catalog, temperature=0.5, feedback=None) -> PlanDraft:
        self._call += 1
        rng = random.Random(
            hash((request.honoree_name, request.guest_count, self._seed, self._call)) & 0xFFFFFFFF
        )
        base = cheapest_compliant_draft(request, catalog)
        if base is None:
            # Even the floor is impossible (e.g. no age-appropriate activity) -> empty draft
            return PlanDraft(theme=request.theme or "Party", venue_sku="VEN-HOME")

        theme = request.theme or rng.choice(
            ["Dinosaurs", "Space Explorers", "Under the Sea", "Superheroes", "Rainbow Magic"]
        )
        base = base.model_copy(update={"theme": theme})

        # Verifier-guided repair: with concrete feedback, the mock (like a real
        # model told exactly what to fix) returns a compliant plan — enriched
        # within budget, since enrichment never violates the verifier.
        if feedback:
            return _enrich_within_budget(base, request, catalog)

        flawed = rng.random() < self._flaw_rate
        if not flawed:
            return _enrich_within_budget(base, request, catalog)

        # Flawed candidate: blow the budget with an expensive add-on (verifier rejects).
        expensive = max(catalog.by_category("activities"), key=lambda i: i.price_for(1, request.guest_count))
        return base.model_copy(update={
            "activities": base.activities + [Selection(sku=expensive.sku, quantity=2)],
        })


def _enrich_within_budget(base: PlanDraft, request, catalog) -> PlanDraft:
    """Budget-aware delight pass: start from the cheapest compliant draft, then
    add a (safe) birthday cake, richer supplies, more age-appropriate
    activities, and premium catering — greedily, never exceeding the budget."""
    guests = request.guest_count
    budget = request.budget
    forbidden = parse_forbidden_allergens(request.dietary_restrictions)
    veg = requires_vegetarian(request.dietary_restrictions)

    def safe(item) -> bool:
        if item.category == "food":
            if forbidden & item.allergens:
                return False
            if veg and not item.vegetarian:
                return False
        return True

    def total_of(d: PlanDraft) -> float:
        t = 0.0
        v = catalog.get(d.venue_sku)
        if v:
            t += v.price_for(1, guests)
        for sel in list(d.food) + list(d.supplies) + list(d.activities):
            it = catalog.get(sel.sku)
            if it:
                t += it.price_for(sel.quantity, guests)
        return t

    d = base
    target = budget * 0.92

    def fits(extra_cost: float) -> bool:
        return total_of(d) + extra_cost <= min(target, budget)

    # 1. every birthday deserves a cake (the safest one that fits)
    have_cake = any((catalog.get(sel.sku) and "cake" in catalog.get(sel.sku).name.lower())
                    for sel in d.food)
    if not have_cake:
        cakes = sorted((c for c in catalog.by_category("food")
                        if "cake" in c.name.lower() and safe(c) and c.serves > 0),
                       key=lambda c: c.unit_price)
        for c in cakes:
            units = max(1, -(-guests // c.serves))
            if fits(c.price_for(units, guests)):
                d = d.model_copy(update={"food": list(d.food) + [Selection(sku=c.sku, quantity=units)]})
                break

    # 2. upgrade supplies to the deluxe pack when it covers everyone and fits
    deluxe = catalog.get("SUP-DELUXE")
    if deluxe and deluxe.serves > 0:
        units = max(1, -(-guests // deluxe.serves))
        cur_sup_cost = sum(catalog.get(sel.sku).price_for(sel.quantity, guests)
                           for sel in d.supplies if catalog.get(sel.sku))
        upgrade_cost = deluxe.price_for(units, guests) - cur_sup_cost
        if upgrade_cost > 0 and fits(upgrade_cost):
            d = d.model_copy(update={"supplies": [Selection(sku=deluxe.sku, quantity=units)]})

    # 3. add distinct age-appropriate activities, best first, while the budget allows
    present = {sel.sku for sel in d.activities}
    candidates = sorted((a for a in catalog.by_category("activities")
                         if a.min_age <= request.honoree_age <= a.max_age
                         and a.sku not in present),
                        key=lambda a: -a.price_for(1, guests))
    hours = max(1, int(getattr(request, "duration_hours", 2.5)))
    for a in candidates:
        qty = hours if a.unit == "per_hour" else 1
        cost = a.price_for(qty, guests)
        if fits(cost):
            d = d.model_copy(update={"activities": list(d.activities) + [Selection(sku=a.sku, quantity=qty)]})
            present.add(a.sku)
        if len(present) >= 6:
            break

    # favor bags for every guest when the budget clearly allows
    favor = catalog.get("SUP-FAVOR")
    if favor and fits(favor.price_for(1, guests)) and total_of(d) < budget * 0.75:
        d = d.model_copy(update={"supplies": list(d.supplies) + [Selection(sku=favor.sku, quantity=1)]})

    # 4. big budgets: add premium catering when it is safe and fits
    cater = catalog.get("FD-CATER")
    if cater and safe(cater) and total_of(d) < budget * 0.5:
        if fits(cater.price_for(1, guests)):
            d = d.model_copy(update={"food": list(d.food) + [Selection(sku=cater.sku, quantity=1)]})

    return d


def build_client() -> LLMClient:
    if settings.LLM_BACKEND == "anthropic":
        logger.info("Using Anthropic backend")
        return AnthropicClient()
    logger.info("Using Mock backend (offline)")
    return MockClient()
