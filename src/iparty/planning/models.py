"""Pydantic models. Plans are built from catalog *selections*; the system prices
them, so the model can never invent a price."""
from __future__ import annotations

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator


class PartyRequest(BaseModel):
    honoree_name: str = Field(..., min_length=1, max_length=100)
    honoree_age: int = Field(..., ge=1, le=120)
    party_date: date
    guest_count: int = Field(..., ge=1, le=500)
    budget: float = Field(..., gt=0)
    theme: str = Field(default="", max_length=120)
    dietary_restrictions: str = Field(default="", max_length=300)
    location_type: Literal["home", "venue", "park", "restaurant"] = "home"
    start_time: str = Field(default="14:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_hours: float = Field(default=2.5, ge=1.0, le=8.0)
    special_requests: str = Field(default="", max_length=500)

    @field_validator("party_date")
    @classmethod
    def not_in_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("party_date cannot be in the past")
        return v

    @field_validator("budget", "duration_hours")
    @classmethod
    def finite_number(cls, v: float) -> float:
        # Reject NaN/Infinity: they bypass budget feasibility (inf affords
        # anything) and crash naive JSON error serialization (NaN).
        if not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v


class Selection(BaseModel):
    """A chosen catalog SKU and how many units. Prices come from the catalog."""
    sku: str
    quantity: int = Field(default=1, ge=1)


class PlanDraft(BaseModel):
    """What the planner (LLM or mock) returns: choices, not prices."""
    theme: str
    venue_sku: str
    food: list[Selection] = Field(default_factory=list)
    supplies: list[Selection] = Field(default_factory=list)
    activities: list[Selection] = Field(default_factory=list)
    schedule: list["ScheduleSlot"] = Field(default_factory=list)
    notes: str = ""


class LineItem(BaseModel):
    sku: str
    category: Literal["venue", "food", "supplies", "activities", "extras"]
    description: str
    quantity: int = Field(default=1, ge=1)
    unit_price: float = Field(..., ge=0)   # set from catalog, never from the model
    subtotal: float = Field(..., ge=0)     # set from catalog


class ScheduleSlot(BaseModel):
    start: str
    end: str
    activity: str = Field(..., min_length=1, max_length=200)


class MenuItem(BaseModel):
    sku: str
    name: str
    servings: int = Field(..., ge=0)
    allergens: list[str] = Field(default_factory=list)   # from catalog, authoritative
    vegetarian: bool = True


class PartyPlan(BaseModel):
    theme: str
    venue: str
    line_items: list[LineItem] = Field(default_factory=list)
    menu: list[MenuItem] = Field(default_factory=list)
    schedule: list[ScheduleSlot] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    supplies: list[str] = Field(default_factory=list)
    notes: str = ""

    @computed_field
    @property
    def total_cost(self) -> float:
        return round(sum(li.subtotal for li in self.line_items), 2)


class Violation(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str


class VerificationReport(BaseModel):
    passed: bool
    score: float
    checks_total: int
    checks_passed: int
    violations: list[Violation] = Field(default_factory=list)


class PlanResult(BaseModel):
    status: Literal["verified", "best_effort"]
    request: PartyRequest
    plan: PartyPlan
    verification: VerificationReport
    telemetry: dict
    backend: str


PlanDraft.model_rebuild()
