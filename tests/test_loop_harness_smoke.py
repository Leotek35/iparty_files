"""Fast in-process version of the 100-loop adversarial harness.

The full harness (scripts/loop_harness.py) drives a live server; this runs the
same invariant checks through TestClient so CI enforces them on every push.
"""
import random
from datetime import date, timedelta

from fastapi.testclient import TestClient

from iparty.api.app import create_app
from iparty.pricing.catalog import (
    StaticCatalog,
    parse_forbidden_allergens,
    requires_vegetarian,
    unverifiable_dietary,
)

CAT = StaticCatalog()
DIETS = ["", "nut allergy", "gluten-free", "vegan", "dairy-free", "coeliac",
         "halal", "kosher", "shellfish allergy", "sesame allergy"]


def test_invariants_hold_across_randomised_profiles():
    c = TestClient(create_app())
    rng = random.Random(1234)
    verified = 0
    for _ in range(60):
        diet = rng.choice(DIETS)
        guests = rng.choice([2, 8, 12, 20, 40, 90])
        budget = rng.choice([40, 120, 350, 700, 1500])
        req = {"honoree_name": rng.choice(["Aria", "José", "小明", "O'Brien"]),
               "honoree_age": rng.choice([2, 5, 8, 13, 16]),
               "party_date": (date.today() + timedelta(days=rng.randint(2, 150))).isoformat(),
               "guest_count": guests, "budget": budget, "theme": rng.choice(["", "Space"]),
               "dietary_restrictions": diet,
               "location_type": rng.choice(["home", "venue", "park"])}
        r = c.post("/api/v1/plan", json=req)
        assert r.status_code in (200, 409), f"unexpected {r.status_code}"
        if r.status_code == 409:
            assert r.json()["detail"]["violations"], "refusal must explain itself"
            continue
        verified += 1
        plan = r.json()["plan"]
        assert plan["total_cost"] <= budget + 0.01, "budget invariant"
        assert sum(m["servings"] for m in plan["menu"]) >= guests, "portion invariant"
        forbidden = parse_forbidden_allergens(diet)
        if forbidden:
            for m in plan["menu"]:
                assert not (forbidden & set(m["allergens"])), f"allergen leak: {m['name']}"
        if requires_vegetarian(diet):
            for m in plan["menu"]:
                item = CAT.get(m["sku"]) if m.get("sku") else None
                assert item is None or item.vegetarian, f"non-vegetarian: {m['name']}"
        assert unverifiable_dietary(diet) is None, "unverifiable diet must fail closed"
    assert verified > 0, "harness produced no verified plans — check the catalog"
