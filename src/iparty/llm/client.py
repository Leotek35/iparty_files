"""LLM client protocol + Anthropic and Mock backends.

The Mock backend is deterministic and offline, so the repo runs and CI passes
with zero secrets. It also occasionally emits an under-budget or under-scaled
plan, which exercises the verifier and the TTL retry/breaker path realistically.
"""
from __future__ import annotations

import json
import random
import re
from typing import Protocol

from ..core.config import settings
from ..core.exceptions import MalformedPlanError
from ..core.logging import get_logger
from ..planning.models import LineItem, MenuItem, PartyPlan, PartyRequest, ScheduleSlot

logger = get_logger("llm")


class LLMClient(Protocol):
    name: str

    async def generate_plan(
        self, system: str, user: str, request: PartyRequest, temperature: float = 0.5
    ) -> PartyPlan: ...


def _parse_plan_json(text: str) -> PartyPlan:
    """Extract and validate a PartyPlan from raw model text."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise MalformedPlanError("no JSON object found in model output")
    try:
        data = json.loads(match.group(0))
        return PartyPlan.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise MalformedPlanError(f"could not parse plan: {exc}") from exc


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------
class AnthropicClient:
    name = "anthropic"

    def __init__(self) -> None:
        from anthropic import AsyncAnthropic  # imported lazily

        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set but LLM_BACKEND=anthropic")
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = settings.ANTHROPIC_MODEL

    async def generate_plan(
        self, system: str, user: str, request: PartyRequest, temperature: float = 0.5
    ) -> PartyPlan:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            temperature=min(1.0, temperature),
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return _parse_plan_json(text)


# ---------------------------------------------------------------------------
# Mock backend (offline, deterministic-ish)
# ---------------------------------------------------------------------------
class MockClient:
    name = "mock"

    def __init__(self, seed: int = 0, flaw_rate: float = 0.45) -> None:
        self._seed = seed
        self._flaw_rate = flaw_rate
        self._call = 0

    async def generate_plan(
        self, system: str, user: str, request: PartyRequest, temperature: float = 0.5
    ) -> PartyPlan:
        # Deterministic per (request, call index) so tests are reproducible.
        self._call += 1
        rng = random.Random(hash((request.honoree_name, request.guest_count, self._seed, self._call)) & 0xFFFFFFFF)
        flawed = rng.random() < self._flaw_rate

        budget = request.budget
        guests = request.guest_count
        theme = request.theme or rng.choice(
            ["Dinosaurs", "Space Explorers", "Under the Sea", "Superheroes", "Rainbow Magic"]
        )

        # Allocate budget across categories
        venue_cost = 0 if request.location_type in ("home", "park") else round(budget * 0.25, 2)
        remaining = budget - venue_cost
        food_budget = round(remaining * 0.40, 2)
        supplies_budget = round(remaining * 0.20, 2)
        activities_budget = round(remaining * 0.30, 2)

        per_head_food = max(1.0, round(food_budget / max(1, guests), 2))
        # A flawed plan under-scales servings or under-spends (verifier should catch it)
        servings = guests + rng.randint(2, 6) if not flawed else max(1, guests - rng.randint(1, 5))

        line_items = [
            LineItem(category="food", description=f"{theme} themed catering", quantity=guests, unit_cost=per_head_food),
            LineItem(category="supplies", description="Plates, cups, napkins, decorations",
                     quantity=1, unit_cost=round(supplies_budget, 2)),
            LineItem(category="activities", description="Entertainment & games",
                     quantity=1, unit_cost=round(activities_budget, 2)),
        ]
        if venue_cost:
            line_items.insert(0, LineItem(category="venue", description=f"{request.location_type} hire",
                                          quantity=1, unit_cost=venue_cost))
        else:
            line_items.insert(0, LineItem(category="venue", description="Home backyard setup",
                                          quantity=1, unit_cost=0.0))

        # Occasionally blow the budget (verifier should reject)
        if flawed and rng.random() < 0.5:
            line_items.append(LineItem(category="extras", description="Surprise fireworks",
                                       quantity=1, unit_cost=round(budget * 0.4, 2)))

        diet = request.dietary_restrictions.strip()
        menu = [
            MenuItem(name="Birthday cake", servings=servings,
                     dietary_tags=[diet] if (diet and not flawed) else []),
            MenuItem(name="Fruit & veggie platter", servings=servings, dietary_tags=[]),
        ]
        notes = ""
        if diet and not flawed:
            notes = f"Menu accounts for dietary restriction: {diet}."

        schedule = [
            ScheduleSlot(start="14:00", end="14:30", activity="Guests arrive & welcome"),
            ScheduleSlot(start="14:30", end="15:30", activity=f"{theme} games & activities"),
            ScheduleSlot(start="15:30", end="16:00", activity="Cake & singing"),
            ScheduleSlot(start="16:00", end="16:30", activity="Free play & goodbyes"),
        ]
        if flawed and rng.random() < 0.4:
            schedule = schedule[:1]  # too short -> verifier rejects

        plan = PartyPlan(
            theme=theme,
            venue="Home backyard" if not venue_cost else f"{request.location_type.title()} venue",
            line_items=line_items,
            menu=menu,
            schedule=schedule,
            activities=[f"{theme} treasure hunt", "Pass the parcel", "Face painting"],
            supplies=["Themed plates", "Cups", "Napkins", "Balloons", "Party favors"],
            notes=notes,
        )
        return plan


def build_client() -> LLMClient:
    if settings.LLM_BACKEND == "anthropic":
        logger.info("Using Anthropic backend")
        return AnthropicClient()
    logger.info("Using Mock backend (offline)")
    return MockClient()
