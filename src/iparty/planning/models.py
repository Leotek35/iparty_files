"""Pydantic models for party requests, plans, and results."""
from __future__ import annotations

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

    @field_validator("party_date")
    @classmethod
    def not_in_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("party_date cannot be in the past")
        return v


class LineItem(BaseModel):
    category: Literal["venue", "food", "supplies", "activities", "extras"]
    description: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1)
    unit_cost: float = Field(..., ge=0)

    @computed_field
    @property
    def subtotal(self) -> float:
        return round(self.quantity * self.unit_cost, 2)


class ScheduleSlot(BaseModel):
    start: str  # "HH:MM"
    end: str    # "HH:MM"
    activity: str = Field(..., min_length=1, max_length=200)


class MenuItem(BaseModel):
    name: str
    servings: int = Field(..., ge=0)
    dietary_tags: list[str] = Field(default_factory=list)


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
    score: float  # fraction of checks passed, 0..1
    checks_total: int
    checks_passed: int
    violations: list[Violation] = Field(default_factory=list)


class PlanResult(BaseModel):
    request: PartyRequest
    plan: PartyPlan
    verification: VerificationReport
    telemetry: dict
    backend: str
