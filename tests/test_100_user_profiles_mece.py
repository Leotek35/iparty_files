"""100-user-profile MECE matrix — the whole demand spectrum in one table.

Seven mutually exclusive partitions that together cover the market the app
can meet (collectively exhaustive by construction):

  1. diy       (001-015)  budget & DIY at-home parties
  2. luxury    (016-030)  high-budget / VIP events
  3. milestone (031-045)  weddings, quinceaneras, mitzvahs, anniversaries
  4. micro     (046-060)  micro-events, studios, pop-ups
  5. tech      (061-076)  tech & gaming events
  6. cultural  (077-090)  cultural & dietary-constrained events
  7. fuzz      (091-100)  boundary, fuzzing & adversarial inputs

Each profile runs the REAL pipeline end to end: request validation
(PartyRequest) -> feasibility precheck -> verified best-of-N planning against
the grounded catalog -> plan-level invariants. Expectations:

  pass             request validates and a VERIFIED plan is produced
  pass_sanitized   as `pass`, plus hostile text is neutralised (data, not code)
  validation_error the request is rejected at the model boundary
  feasibility_error the planner refuses honestly with the minimum budget
  email_error      the contact email is rejected by the email gate
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from iparty.core.emailcheck import validate_email_address
from iparty.core.exceptions import NoValidPlanError
from iparty.llm.client import MockClient
from iparty.orchestration.ttl_engine import TTLOrchestrator
from iparty.planning.models import PartyRequest
from iparty.planning.planner import TTLPartyPlanner
from iparty.pricing.catalog import StaticCatalog

FUTURE = date.today() + timedelta(days=45)

PROFILES_MECE = [
    # Partition 1: Budget & DIY (001-015)
    {"id": "001", "name": "Elena Rostova", "guests": 12, "budget": 250.0, "theme": "DIY Birthday", "cat": "diy", "expect": "pass"},
    {"id": "002", "name": "Marcus Vance", "guests": 25, "budget": 450.0, "theme": "Backyard BBQ", "cat": "diy", "expect": "pass"},
    {"id": "003", "name": "Amina Diallo", "guests": 20, "budget": 300.0, "theme": "Baby Shower", "cat": "diy", "expect": "pass"},
    {"id": "004", "name": "Chloe Bennett", "guests": 35, "budget": 600.0, "theme": "Graduation", "cat": "diy", "expect": "pass"},
    {"id": "005", "name": "Devon Miller", "guests": 8, "budget": 150.0, "theme": "Game Night", "cat": "diy", "expect": "pass"},
    {"id": "006", "name": "Sofia Rossi", "guests": 15, "budget": 350.0, "theme": "1st Birthday", "cat": "diy", "expect": "pass"},
    {"id": "007", "name": "Liam O Connor", "guests": 30, "budget": 500.0, "theme": "Housewarming", "cat": "diy", "expect": "pass"},
    {"id": "008", "name": "Hannah Schmidt", "guests": 10, "budget": 280.0, "theme": "Craft and Sip", "cat": "diy", "expect": "pass"},
    {"id": "009", "name": "Tariq Mansour", "guests": 18, "budget": 400.0, "theme": "Retirement Tea", "cat": "diy", "expect": "pass"},
    {"id": "010", "name": "Grace Kelly", "guests": 14, "budget": 320.0, "theme": "Movie Night", "cat": "diy", "expect": "pass"},
    {"id": "011", "name": "Oscar Lindqvist", "guests": 16, "budget": 480.0, "theme": "Friendsgiving", "cat": "diy", "expect": "pass"},
    {"id": "012", "name": "Priya Nair", "guests": 22, "budget": 550.0, "theme": "Mehndi Night", "cat": "diy", "expect": "pass"},
    {"id": "013", "name": "Caleb Wright", "guests": 40, "budget": 500.0, "theme": "Tailgate Party", "cat": "diy", "expect": "pass"},
    {"id": "014", "name": "Zoe Kastner", "guests": 9, "budget": 200.0, "theme": "Book Club Soirée", "cat": "diy", "expect": "pass"},
    {"id": "015", "name": "Mateo Hernandez", "guests": 15, "budget": 300.0, "theme": "Pet Birthday", "cat": "diy", "expect": "pass"},
    # Partition 2: Luxury & VIP (016-030)
    {"id": "016", "name": "Victoria Sterling", "guests": 250, "budget": 85000.0, "theme": "Charity Gala", "cat": "luxury", "expect": "pass"},
    {"id": "017", "name": "Julian Kensington", "guests": 20, "budget": 12000.0, "theme": "VC Dinner", "cat": "luxury", "expect": "pass"},
    {"id": "018", "name": "Arthur Pendelton", "guests": 180, "budget": 50000.0, "theme": "Medical Gala", "cat": "luxury", "expect": "pass"},
    {"id": "019", "name": "Svetlana Voronova", "guests": 120, "budget": 45000.0, "theme": "Haute Couture", "cat": "luxury", "expect": "pass"},
    {"id": "020", "name": "Harrison Blake", "guests": 150, "budget": 35000.0, "theme": "Series B Party", "cat": "luxury", "expect": "pass"},
    {"id": "021", "name": "Camilla De La Tour", "guests": 80, "budget": 28000.0, "theme": "Anniversary", "cat": "luxury", "expect": "pass"},
    {"id": "022", "name": "Nathaniel Drake", "guests": 300, "budget": 95000.0, "theme": "Product Reveal", "cat": "luxury", "expect": "pass"},
    {"id": "023", "name": "Isabella Fontanelli", "guests": 45, "budget": 22000.0, "theme": "Yacht Party", "cat": "luxury", "expect": "pass"},
    {"id": "024", "name": "Reginald Thorne", "guests": 60, "budget": 40000.0, "theme": "Wine Auction", "cat": "luxury", "expect": "pass"},
    {"id": "025", "name": "Seraphina Vance", "guests": 110, "budget": 38000.0, "theme": "Polo Luncheon", "cat": "luxury", "expect": "pass"},
    {"id": "026", "name": "Alexander Cross", "guests": 90, "budget": 25000.0, "theme": "Speakeasy Retreat", "cat": "luxury", "expect": "pass"},
    {"id": "027", "name": "Giselle Beaulieu", "guests": 140, "budget": 18000.0, "theme": "Art Vernissage", "cat": "luxury", "expect": "pass"},
    {"id": "028", "name": "Maximilian Vance", "guests": 16, "budget": 15000.0, "theme": "Executive Summit", "cat": "luxury", "expect": "pass"},
    {"id": "029", "name": "Octavia Spencer", "guests": 200, "budget": 70000.0, "theme": "Debutante Ball", "cat": "luxury", "expect": "pass"},
    {"id": "030", "name": "Christian Laurent", "guests": 30, "budget": 110000.0, "theme": "Island Pop-Up", "cat": "luxury", "expect": "pass"},
    # Partition 3: Milestones & Weddings (031-045)
    {"id": "031", "name": "Fatima and Omar", "guests": 300, "budget": 35000.0, "theme": "Wedding", "cat": "milestone", "expect": "pass"},
    {"id": "032", "name": "Jessica and David", "guests": 110, "budget": 18000.0, "theme": "Barn Wedding", "cat": "milestone", "expect": "pass"},
    {"id": "033", "name": "Deepak and Ananya", "guests": 350, "budget": 45000.0, "theme": "Sangeet", "cat": "milestone", "expect": "pass"},
    {"id": "034", "name": "Sarah Jenkins", "guests": 60, "budget": 6500.0, "theme": "Sweet 16", "cat": "milestone", "expect": "pass"},
    {"id": "035", "name": "Carlos Gomez", "guests": 180, "budget": 15000.0, "theme": "Quinceanera", "cat": "milestone", "expect": "pass"},
    {"id": "036", "name": "Brenda MacIntyre", "guests": 75, "budget": 8000.0, "theme": "Golden 50th", "cat": "milestone", "expect": "pass"},
    {"id": "037", "name": "Raymond Liu", "guests": 120, "budget": 20000.0, "theme": "Bar Mitzvah", "cat": "milestone", "expect": "pass"},
    {"id": "038", "name": "Rachel Rosen", "guests": 100, "budget": 18000.0, "theme": "Bat Mitzvah", "cat": "milestone", "expect": "pass"},
    {"id": "039", "name": "Tanya Washington", "guests": 90, "budget": 5500.0, "theme": "Family Reunion", "cat": "milestone", "expect": "pass"},
    {"id": "040", "name": "Lucas van der Berg", "guests": 80, "budget": 9000.0, "theme": "21st Festival", "cat": "milestone", "expect": "pass"},
    {"id": "041", "name": "Mei-Ling Zhou", "guests": 50, "budget": 4500.0, "theme": "100-Day Party", "cat": "milestone", "expect": "pass"},
    {"id": "042", "name": "Anthony Russo", "guests": 65, "budget": 7200.0, "theme": "Italian Anniversary", "cat": "milestone", "expect": "pass"},
    {"id": "043", "name": "Nia Adebayo", "guests": 85, "budget": 6000.0, "theme": "Naming Ceremony", "cat": "milestone", "expect": "pass"},
    {"id": "044", "name": "Ingrid Bergman", "guests": 40, "budget": 4200.0, "theme": "Midsummer Feast", "cat": "milestone", "expect": "pass"},
    {"id": "045", "name": "Kyle Peterson", "guests": 45, "budget": 5000.0, "theme": "Surprise 40th", "cat": "milestone", "expect": "pass"},
    # Partition 4: Micro-Events & Studios (046-060)
    {"id": "046", "name": "Zackary Taylor", "guests": 35, "budget": 2500.0, "theme": "Live Podcast", "cat": "micro", "expect": "pass"},
    {"id": "047", "name": "Luna Lovecraft", "guests": 50, "budget": 3000.0, "theme": "Gothic Release", "cat": "micro", "expect": "pass"},
    {"id": "048", "name": "Kenji Sato", "guests": 16, "budget": 1200.0, "theme": "Coffee Cupping", "cat": "micro", "expect": "pass"},
    {"id": "049", "name": "Maya Lin", "guests": 70, "budget": 4800.0, "theme": "Fashion Pop-Up", "cat": "micro", "expect": "pass"},
    {"id": "050", "name": "Elijah Woods", "guests": 40, "budget": 1800.0, "theme": "Secret Gig", "cat": "micro", "expect": "pass"},
    {"id": "051", "name": "Nadia Kowalska", "guests": 12, "budget": 1500.0, "theme": "Pottery Studio", "cat": "micro", "expect": "pass"},
    {"id": "052", "name": "Rory Gallagher", "guests": 60, "budget": 3200.0, "theme": "Tap Takeover", "cat": "micro", "expect": "pass"},
    {"id": "053", "name": "Tara Deshmukh", "guests": 25, "budget": 2000.0, "theme": "Sound Bath", "cat": "micro", "expect": "pass"},
    {"id": "054", "name": "Felix Baum", "guests": 30, "budget": 1600.0, "theme": "Secret Cinema", "cat": "micro", "expect": "pass"},
    {"id": "055", "name": "Clara Schumann", "guests": 22, "budget": 2400.0, "theme": "Chamber Music", "cat": "micro", "expect": "pass"},
    {"id": "056", "name": "Dante Alighieri", "guests": 45, "budget": 1100.0, "theme": "Poetry Slam", "cat": "micro", "expect": "pass"},
    {"id": "057", "name": "Naomi Jones", "guests": 30, "budget": 6000.0, "theme": "Beauty Masterclass", "cat": "micro", "expect": "pass"},
    {"id": "058", "name": "Gideon Cross", "guests": 20, "budget": 7500.0, "theme": "Watch Meetup", "cat": "micro", "expect": "pass"},
    {"id": "059", "name": "Hana Kim", "guests": 18, "budget": 1800.0, "theme": "Skincare Lab", "cat": "micro", "expect": "pass"},
    {"id": "060", "name": "Lars Ulrich", "guests": 25, "budget": 1400.0, "theme": "Vinyl Session", "cat": "micro", "expect": "pass"},
    # Partition 5: Tech & Gaming (061-076)
    {"id": "061", "name": "Anil Gupta", "guests": 120, "budget": 14000.0, "theme": "AI Hackathon", "cat": "tech", "expect": "pass"},
    {"id": "062", "name": "Samira Khan", "guests": 64, "budget": 8000.0, "theme": "LAN Tournament", "cat": "tech", "expect": "pass"},
    {"id": "063", "name": "Cody Martin", "guests": 16, "budget": 2200.0, "theme": "VR Arcade", "cat": "tech", "expect": "pass"},
    {"id": "064", "name": "Tyler Durden", "guests": 50, "budget": 3800.0, "theme": "Retro Arcade", "cat": "tech", "expect": "pass"},
    {"id": "065", "name": "Evelyn Reed", "guests": 24, "budget": 3500.0, "theme": "Cyberpunk Mystery", "cat": "tech", "expect": "pass"},
    {"id": "066", "name": "Rajiv Patel", "guests": 40, "budget": 5500.0, "theme": "Drone Racing", "cat": "tech", "expect": "pass"},
    {"id": "067", "name": "Zoe Quinn", "guests": 30, "budget": 900.0, "theme": "Boardgame Test", "cat": "tech", "expect": "pass"},
    {"id": "068", "name": "Goran Ivan", "guests": 90, "budget": 7000.0, "theme": "Robotics Expo", "cat": "tech", "expect": "pass"},
    {"id": "069", "name": "Brenden Eich", "guests": 45, "budget": 2800.0, "theme": "OSS Meetup", "cat": "tech", "expect": "pass"},
    {"id": "070", "name": "Kiran Mazum", "guests": 60, "budget": 6500.0, "theme": "Biotech Pitch", "cat": "tech", "expect": "pass"},
    {"id": "071", "name": "Soren Kierk", "guests": 28, "budget": 3200.0, "theme": "Escape Puzzle", "cat": "tech", "expect": "pass"},
    {"id": "072", "name": "Mia Khalifa", "guests": 12, "budget": 4500.0, "theme": "Stream Studio", "cat": "tech", "expect": "pass"},
    {"id": "073", "name": "Dmitri Shost", "guests": 20, "budget": 1600.0, "theme": "Modular Jam", "cat": "tech", "expect": "pass"},
    {"id": "074", "name": "Jocelyn Wild", "guests": 36, "budget": 4000.0, "theme": "Laser Tag", "cat": "tech", "expect": "pass"},
    {"id": "075", "name": "Toby Fox", "guests": 75, "budget": 3200.0, "theme": "8-Bit Dance", "cat": "tech", "expect": "pass"},
    {"id": "076", "name": "Carlos Santoro", "guests": 40, "budget": 3000.0, "theme": "Tabletop Cafe", "cat": "tech", "expect": "pass"},
    # Partition 6: Cultural & Dietary Constraints (077-090)
    {"id": "077", "name": "Leila Al-Mansoor", "guests": 120, "budget": 16000.0, "theme": "Halal Engagement", "cat": "cultural", "expect": "pass"},
    {"id": "078", "name": "Yossi Shapiro", "guests": 140, "budget": 24000.0, "theme": "Glatt Kosher Feast", "cat": "cultural", "expect": "pass"},
    {"id": "079", "name": "Sunita and Rohan", "guests": 250, "budget": 65000.0, "theme": "3-Day Shaadi", "cat": "cultural", "expect": "pass"},
    {"id": "080", "name": "Jean-Luc Picard", "guests": 85, "budget": 14000.0, "theme": "Gluten Free Gala", "cat": "cultural", "expect": "pass", "dietary": "gluten free"},
    {"id": "081", "name": "Tenzen Norbu", "guests": 150, "budget": 7500.0, "theme": "Losar New Year", "cat": "cultural", "expect": "pass"},
    {"id": "082", "name": "Chiamaka Okonjo", "guests": 280, "budget": 38000.0, "theme": "Nigerian Traditional", "cat": "cultural", "expect": "pass"},
    {"id": "083", "name": "Siddharth Verma", "guests": 100, "budget": 9000.0, "theme": "Jain Pure Veg", "cat": "cultural", "expect": "pass", "dietary": "vegetarian"},
    {"id": "084", "name": "Katarina Milos", "guests": 45, "budget": 3200.0, "theme": "Serbian Slava", "cat": "cultural", "expect": "pass"},
    {"id": "085", "name": "Hiroshi Tanaka", "guests": 14, "budget": 4800.0, "theme": "Kaiseki Experience", "cat": "cultural", "expect": "pass"},
    {"id": "086", "name": "Thandiwe Khumalo", "guests": 110, "budget": 6200.0, "theme": "Heritage Braai", "cat": "cultural", "expect": "pass"},
    {"id": "087", "name": "Alejandro Morales", "guests": 90, "budget": 5800.0, "theme": "Dia de los Muertos", "cat": "cultural", "expect": "pass"},
    {"id": "088", "name": "Fiona MacLeod", "guests": 70, "budget": 5000.0, "theme": "Burns Supper", "cat": "cultural", "expect": "pass"},
    {"id": "089", "name": "Eleni Papadopoulos", "guests": 130, "budget": 12000.0, "theme": "Greek Baptism", "cat": "cultural", "expect": "pass"},
    {"id": "090", "name": "Lian Hua", "guests": 80, "budget": 7200.0, "theme": "Moon Festival", "cat": "cultural", "expect": "pass"},
    # Partition 7: Boundary, Fuzzing & Adversarial (091-100)
    {"id": "091", "name": "Fuzz Alpha", "guests": 20, "budget": -5000.0, "theme": "Negative Budget", "cat": "fuzz", "expect": "validation_error"},
    {"id": "092", "name": "Fuzz Beta", "guests": 0, "budget": 1500.0, "theme": "Zero Guests", "cat": "fuzz", "expect": "validation_error"},
    {"id": "093", "name": "Fuzz Gamma", "guests": 150000, "budget": 10000000.0, "theme": "Integer Overflow", "cat": "fuzz", "expect": "validation_error"},
    {"id": "094", "name": "Adversary Delta", "guests": 25, "budget": 3000.0, "theme": "'; DROP TABLE bookings; --", "cat": "fuzz", "expect": "pass_sanitized"},
    {"id": "095", "name": "Adversary Epsilon", "guests": 15, "budget": 1200.0, "theme": "\U0001F389\U0001F525\u0000\uffff", "cat": "fuzz", "expect": "pass_sanitized"},
    {"id": "096", "name": "Fuzz Zeta", "guests": 100, "budget": 10.0, "theme": "Under Floor Ratio", "cat": "fuzz", "expect": "feasibility_error"},
    {"id": "097", "name": "Fuzz Eta", "guests": 1, "budget": 500.0, "theme": "Single Guest Boundary", "cat": "fuzz", "expect": "pass"},
    {"id": "098", "name": "Fuzz Theta", "guests": 30, "budget": 2500.0, "theme": "Unicode Cyrillic テスト", "cat": "fuzz", "expect": "pass"},
    {"id": "099", "name": "Fuzz Iota", "guests": 10, "budget": 800.0, "email": "user@malformed..com", "theme": "Bad Domain", "cat": "fuzz", "expect": "email_error"},
    {"id": "100", "name": "Fuzz Kappa", "guests": 5, "budget": 400.0, "email": "test@disposablemail.com", "theme": "Disposable Mail", "cat": "fuzz", "expect": "email_error"},
]

# Honoree age synthesised from the occasion (drives age-appropriateness checks).
_AGE_BY_THEME_KEY = {
    "1st birthday": 1, "100-day": 1, "baby shower": 30, "naming ceremony": 1,
    "sweet 16": 16, "quinceanera": 15, "bar mitzvah": 13, "bat mitzvah": 13,
    "21st": 21, "surprise 40th": 40, "golden 50th": 50, "retirement": 65,
}

# Partition -> venue type (galas and studios book venues; DIY stays home).
_LOCATION_BY_CAT = {
    "diy": "home", "luxury": "venue", "milestone": "venue", "micro": "venue",
    "tech": "venue", "cultural": "venue", "fuzz": "home",
}


def _honoree_age(profile: dict) -> int:
    theme = profile["theme"].lower()
    for key, age in _AGE_BY_THEME_KEY.items():
        if key in theme:
            return age
    return 30


def build_request(profile: dict) -> PartyRequest:
    """Map a MECE profile onto the app's real request model."""
    return PartyRequest(
        honoree_name=profile["name"],
        honoree_age=_honoree_age(profile),
        party_date=FUTURE,
        guest_count=profile["guests"],
        budget=profile["budget"],
        theme=profile["theme"],
        dietary_restrictions=profile.get("dietary", ""),
        location_type=_LOCATION_BY_CAT[profile["cat"]],
    )


def _fresh_planner(profile_id: str) -> tuple[TTLPartyPlanner, StaticCatalog]:
    """Deterministic, isolated pipeline per profile: no cross-profile state."""
    catalog = StaticCatalog()
    planner = TTLPartyPlanner(
        MockClient(seed=int(profile_id)), catalog, TTLOrchestrator(name=f"mece-{profile_id}")
    )
    return planner, catalog


def test_profiles_are_mutually_exclusive():
    """MECE property: 100 unique IDs, each in exactly one of the 7 partitions."""
    ids = [p["id"] for p in PROFILES_MECE]
    assert len(ids) == len(set(ids)) == 100, "Profile IDs must be unique and total 100."
    categories = {p["cat"] for p in PROFILES_MECE}
    assert categories == {"diy", "luxury", "milestone", "micro", "tech", "cultural", "fuzz"}
    sizes = {c: sum(1 for p in PROFILES_MECE if p["cat"] == c) for c in categories}
    assert sum(sizes.values()) == 100  # collectively exhaustive over the table


def test_expectation_labels_are_a_closed_set():
    allowed = {"pass", "pass_sanitized", "validation_error", "feasibility_error", "email_error"}
    assert {p["expect"] for p in PROFILES_MECE} <= allowed


@pytest.mark.parametrize("p", PROFILES_MECE, ids=[f"ID-{p['id']}-{p['cat']}" for p in PROFILES_MECE])
async def test_mece_profile_execution_matrix(p):
    expect = p["expect"]

    # 1. Email gate (profiles that carry a contact email)
    if "email" in p:
        valid_email = validate_email_address(p["email"])
        if expect == "email_error":
            assert not valid_email, f"Profile {p['id']} allowed invalid email: {p['email']}"
            return
        assert valid_email, f"Profile {p['id']} rejected a legitimate email: {p['email']}"

    # 2. Request-model validation
    try:
        req = build_request(p)
    except (ValueError, ValidationError):
        assert expect == "validation_error", f"Profile {p['id']} raised unexpected validation error."
        return
    assert expect != "validation_error", f"Profile {p['id']} should have been rejected at validation."

    # 3. Feasibility + verified planning (the real pipeline, mock backend)
    planner, catalog = _fresh_planner(p["id"])
    try:
        result = await planner.plan(req)
    except NoValidPlanError as exc:
        assert expect == "feasibility_error", (
            f"Profile {p['id']} was refused unexpectedly: {exc.message} {exc.violations}"
        )
        assert exc.minimum_feasible_budget is not None
        assert exc.minimum_feasible_budget > req.budget
        return
    assert expect != "feasibility_error", f"Profile {p['id']} passed feasibility but should have failed."

    # 4. Verified-plan invariants: budget, scaling, and catalog grounding
    assert result.status == "verified" and result.verification.passed
    plan = result.plan
    assert plan.total_cost <= req.budget + 0.01, f"Profile {p['id']} plan exceeds budget."
    assert sum(m.servings for m in plan.menu) >= req.guest_count
    for li in plan.line_items:
        item = catalog.get(li.sku)
        assert item is not None, f"Catalog grounding failed: unknown SKU {li.sku} in profile {p['id']}"
        assert abs(item.price_for(li.quantity, req.guest_count) - li.subtotal) <= 0.01

    # 5. Hostile text stays data: control chars stripped, content not executed
    if expect == "pass_sanitized":
        assert "\x00" not in req.theme and "\x00" not in plan.theme
        if p["id"] == "094":
            # SQL-looking text survives untouched as inert data.
            assert plan.theme == p["theme"]
        if p["id"] == "095":
            assert "🎉" in plan.theme  # legitimate unicode/emoji preserved
