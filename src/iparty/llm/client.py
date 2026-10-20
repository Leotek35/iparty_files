"""LLM client protocol + Anthropic and Mock backends.

Backends return a PlanDraft (catalog SELECTIONS, never prices). Both start
from the Party Concept composer:

* MockClient serves the composer's verified concept for the candidate's
  temperature (variant 0, 1, 2 ...) — offline, deterministic, and good — so
  the repo runs and CI passes with zero secrets, and so the demo looks like
  the product. An optional flaw rate re-introduces broken candidates to
  exercise the verifier / best-of-N path.
* AnthropicClient sends the model the catalog slice plus the composer's
  concept as a VERIFIED STARTING POINT, and asks for a richer one. Whatever
  comes back is verified like any other candidate.
"""
from __future__ import annotations

import json
import random
import re
from typing import Protocol

from ..core.config import settings
from ..core.exceptions import MalformedPlanError
from ..core.logging import get_logger
from ..planning.composer import compose
from ..planning.feasibility import cheapest_compliant_draft
from ..planning.models import PartyRequest, PlanDraft, Selection
from ..planning.prompts import SYSTEM_PROMPT, build_user_prompt
from ..pricing.catalog import Catalog

logger = get_logger("llm")

_BASE_TEMPERATURE, _TEMPERATURE_STEP = 0.4, 0.15


def variant_for(temperature: float) -> int:
    """The planner raises temperature per candidate (0.4, 0.55, 0.7, ...); map
    that back to a composer variant (0, 1, 2, ...)."""
    return max(0, int((temperature - _BASE_TEMPERATURE) / _TEMPERATURE_STEP + 1e-6))


def baseline_draft(request: PartyRequest, catalog: Catalog, variant: int = 0) -> PlanDraft | None:
    """The best verified draft we can build without a model: the composer's
    concept for this variant, else variant 0, else the cheapest compliant plan."""
    draft = compose(request, catalog, variant=variant)
    if draft is None and variant:
        draft = compose(request, catalog)
    if draft is None:
        draft = cheapest_compliant_draft(request, catalog)
    return draft


class LLMClient(Protocol):
    name: str

    async def generate_draft(
        self, request: PartyRequest, catalog: Catalog,
        temperature: float = 0.5, feedback: str | None = None,
    ) -> PlanDraft: ...


def _parse_draft_json(text: str) -> PlanDraft:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise MalformedPlanError("no JSON object found in model output")
    try:
        return PlanDraft.model_validate(json.loads(match.group(0)))
    except Exception as exc:
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
        variant = variant_for(temperature)
        baseline = baseline_draft(request, catalog, variant)
        user = build_user_prompt(request, catalog, baseline=baseline, variant=variant)
        if feedback:
            user += ("\n\nIMPORTANT — your previous selection failed verification:\n"
                     + feedback + "\nReturn a corrected JSON concept.")
        resp = await self._client.messages.create(
            model=self._model, max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            temperature=min(1.0, temperature), system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return _parse_draft_json(text)


class MockClient:
    """Offline planner: the composer's verified concept for each candidate.

    `flaw_rate` > 0 makes some candidates deliberately over budget (an
    expensive activity added twice) so the verifier / best-of-N / repair path
    is exercised in tests; the default is 0 so the product demo is clean."""

    name = "mock"

    def __init__(self, seed: int = 0, flaw_rate: float | None = None) -> None:
        self._seed = seed
        self._flaw_rate = settings.MOCK_FLAW_RATE if flaw_rate is None else flaw_rate
        self._call = 0

    async def generate_draft(self, request, catalog, temperature=0.5, feedback=None) -> PlanDraft:
        self._call += 1
        rng = random.Random(
            hash((request.honoree_name, request.guest_count, self._seed, self._call)) & 0xFFFFFFFF
        )
        variant = variant_for(temperature)
        base = baseline_draft(request, catalog, variant)
        if base is None:
            # Even the floor is impossible (e.g. no age-appropriate activity) -> empty draft
            return PlanDraft(theme=request.theme or "Party", venue_sku="VEN-HOME")
        # Verifier-guided repair: with concrete feedback, the mock (like a real
        # model told exactly what to fix) returns the compliant concept.
        if feedback or rng.random() >= self._flaw_rate:
            return base
        # Flawed candidate: blow the budget with an expensive add-on (verifier rejects).
        eligible = [a for a in catalog.by_category("activities")
                    if a.min_age <= request.honoree_age <= a.max_age]
        expensive = max(eligible or catalog.by_category("activities"),
                        key=lambda i: i.price_for(1, request.guest_count))
        return base.model_copy(update={
            "activities": base.activities + [Selection(sku=expensive.sku, quantity=2)],
        })


def build_client() -> LLMClient:
    if settings.LLM_BACKEND == "anthropic":
        logger.info("Using Anthropic backend")
        return AnthropicClient()
    logger.info("Using Mock backend (offline, composer-backed)")
    return MockClient()
