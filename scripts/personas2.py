"""Suite 2 — 150 personas, substantially harder than suite 1.

Every persona stacks 3+ constraints, sits exactly on a boundary, speaks a
language the parser doesn't, or belongs to a repeat-customer cohort that tests
whether the JEPA-TTL bridge actually LEARNS the workload over time.

expect_status semantics:
  200    — must produce a verified plan
  422    — must reject malformed input
  409    — must refuse (impossible)
  "flex" — 200 OR an honest 409 that includes minimum_feasible_budget
"""
from __future__ import annotations
from datetime import date, timedelta

TODAY = date.today()
def d(days): return (TODAY + timedelta(days=days)).isoformat()

def P(pid, name, story, payload, expect_status=200, forbid=None, want_veg=False,
      want_features=None, luxury=False, tag=""):
    return {"id": pid, "name": name, "story": story, "payload": payload,
            "expect_status": expect_status, "forbid_allergens": forbid or [],
            "want_vegetarian": want_veg, "want_features": want_features or [],
            "luxury": luxury, "tag": tag}

def req(name, age, days, guests, budget, theme="", diet="", loc="home", **over):
    r = {"honoree_name": name, "honoree_age": age, "party_date": d(days),
         "guest_count": guests, "budget": budget, "theme": theme,
         "dietary_restrictions": diet, "location_type": loc}
    r.update(over)
    return r

PERSONAS = []
A = PERSONAS.append
n = 0


def nid():
    global n
    n += 1
    return f"q{n:03d}"

# ---- 30 boundary surfers
BOUNDS = [
    ("guests 12 == veggie platter serves", req("B1", 7, 20, 12, 200.0, diet="vegan")),
    ("guests 13, one over the platter", req("B2", 7, 21, 13, 200.0, diet="vegan")),
    ("guests 16 == basic pack capacity", req("B3", 7, 22, 16, 300.0)),
    ("guests 17, one place setting over", req("B4", 7, 23, 17, 300.0)),
    ("guests 20 == cake servings", req("B5", 7, 24, 20, 350.0)),
    ("guests 21, cake +1", req("B6", 7, 25, 21, 350.0)),
    ("age 3 == bounce house min", req("B7", 3, 26, 10, 600.0)),
    ("age 2, one under bounce min", req("B8", 2, 27, 10, 600.0)),
    ("age 12 == bounce house max", req("B9", 12, 28, 10, 600.0)),
    ("age 13, one over bounce max", req("B10", 13, 29, 10, 600.0)),
    ("age 8 == karaoke min", req("B11", 8, 30, 10, 800.0)),
    ("age 120 == validation max", req("B12", 120, 31, 10, 800.0)),
    ("duration 1h == minimum", req("B13", 7, 32, 10, 400.0, duration_hours=1.0)),
    ("duration 8h == maximum", req("B14", 7, 33, 10, 400.0, duration_hours=8.0)),
    ("start 23:00 + 6h must clamp at midnight", req("B15", 7, 34, 10, 400.0, start_time="23:00", duration_hours=6.0)),
    ("start 00:00 midnight party", req("B16", 19, 35, 10, 400.0, start_time="00:00")),
    ("budget exactly $40 floor for 8", req("B17", 7, 36, 8, 40.0)),
    ("budget $39.99, one cent under floor", req("B18", 7, 37, 8, 39.99), "flex"),
    ("guest 1, budget $14 (floor ~14.5)", req("B19", 7, 38, 1, 14.0), "flex"),
    ("guests 500 park vegan on $8000", req("B20", 7, 39, 500, 8000.0, "", "vegan", "park")),
    ("date tomorrow", req("B21", 7, 1, 10, 300.0)),
    ("date 365 days out", req("B22", 7, 365, 10, 300.0)),
    ("theme exactly 120 chars", req("B23", 7, 40, 10, 300.0, theme="T" * 120)),
    ("diet exactly 300 chars", req("B24", 7, 41, 10, 300.0, diet=("nut allergy, " * 23)[:300])),
    ("special requests exactly 500 chars", req("B25", 7, 42, 10, 300.0, special_requests="w" * 500)),
    ("budget 1 billion", req("B26", 7, 43, 10, 1e9), 200),
    ("restaurant floor: 10 guests * $22 + extras", req("B27", 7, 44, 10, 290.0), "flex"),
    ("age 1 with only baby-safe catalog rows", req("B28", 1, 45, 8, 250.0)),
    ("guests 499", req("B29", 7, 46, 499, 7000.0, "", "", "park")),
    ("budget $0.02", req("B30", 7, 47, 5, 0.02), 409),
]
for story, payload, *st in BOUNDS:
    A(P(nid(), f"Boundary {n+1}", story, payload, expect_status=(st[0] if st else 200), tag="boundary"))

# ---- 30 compound stackers
STACKS = [
    ("vegan + GF + sesame, evening park, 120 guests, rain plan", req("S1", 9, 50, 120, 2400.0, "Eco Carnival", "vegan, gluten-free, sesame allergy", "park", start_time="17:00", duration_hours=4.0, special_requests="rain backup; accessibility"), ["milk","egg","fish","shellfish","wheat","sesame"], True),
    ("kosher restaurant 60 guests, wheelchair + AV, 3h", req("S2", 65, 51, 60, 3500.0, "Golden Jubilee", "kosher", "restaurant", duration_hours=3.0, special_requests="wheelchair access; av equipment"), [], True),
    ("halal + nut allergy park brunch 80 guests", req("S3", 10, 52, 80, 1800.0, "", "halal, nut allergy", "park", start_time="10:00"), ["peanut","tree_nut"], True),
    ("all-9 allergens, 200 guests, venue, 6h", req("S4", 8, 53, 200, 6000.0, "", "peanut tree nut egg milk wheat soy fish shellfish sesame allergies", "venue", duration_hours=6.0), ["peanut","tree_nut","egg","milk","wheat","soy","fish","shellfish","sesame"], False),
    ("vegan teen 16th, DJ + photo booth, evening", req("S5", 16, 54, 40, 2500.0, "Neon Nights", "vegan", "venue", start_time="19:00", duration_hours=4.0), ["milk","egg","fish","shellfish"], True),
    ("toddler 2, milk+egg allergy, home, 1.5h nap-window", req("S6", 2, 55, 12, 450.0, "", "milk and egg allergies", "home", start_time="10:00", duration_hours=1.5), ["milk","egg"], False),
    ("90th, soft food, quiet, accessible restaurant", req("S7", 90, 56, 30, 1600.0, "", "", "restaurant", special_requests="soft food; quiet music; wheelchair access"), [], False),
    ("celiac + lactose, 45 kids, park, surprise", req("S8", 7, 57, 45, 1100.0, "", "celiac and lactose intolerant", "park", special_requests="surprise party"), ["wheat","milk"], False),
    ("pescatarian 250-guest block party 5h", req("S9", 12, 58, 250, 5200.0, "", "pescatarian", "park", duration_hours=5.0), [], True),
    ("jain, 35 guests, venue, bilingual", req("S10", 11, 59, 35, 1500.0, "", "jain", "venue", special_requests="bilingual hosting"), [], True),
]
for story, payload, forbid, veg in STACKS:
    A(P(nid(), f"Stacker {n+1}", story, payload, expect_status="flex", forbid=forbid, want_veg=veg, tag="compound"))
for i in range(20):
    diet = ["vegan and wheat allergy", "vegetarian, soy and sesame allergies", "nut and egg allergies",
            "kosher and nut allergy", "halal, dairy-free"][i % 5]
    loc = ["home", "park", "venue", "restaurant"][i % 4]
    A(P(nid(), f"Stacker-gen {i}", f"generated stack {i}: {diet} at {loc}, evening, favors",
        req(f"SG{i}", 4 + i, 60 + i, 25 + 7 * i, 900.0 + 260.0 * i, f"Theme{i}", diet, loc,
            start_time=f"{10 + i % 12:02d}:30", duration_hours=1.5 + (i % 6),
            special_requests="accessibility; parking info" if i % 2 else "weather backup; music playlist"),
        expect_status="flex",
        forbid={"vegan and wheat allergy": ["milk","egg","fish","shellfish","wheat"],
                "vegetarian, soy and sesame allergies": ["soy","sesame"],
                "nut and egg allergies": ["peanut","tree_nut","egg"],
                "kosher and nut allergy": ["peanut","tree_nut"],
                "halal, dairy-free": ["milk"]}[diet],
        want_veg=("vegan" in diet or "vegetarian" in diet or "kosher" in diet or "halal" in diet),
        tag="compound"))

# ---- 20 multilingual & messy dietary text
LANGS = [("sin gluten", "Spanish gluten-free"), ("sans arachide", "French no-peanut"),
         ("無麩質", "Chinese gluten-free"), ("халяль", "Russian halal"),
         ("kein Gluten bitte", "German gluten-free"), ("glutenvrij", "Dutch"),
         ("senza glutine", "Italian"), ("グルテンフリー", "Japanese"),
         ("bez glutenu", "Polish"), ("فقط حلال", "Arabic halal-only"),
         ("no maní por favor", "Spanish no-peanut"), ("laktosefrei", "German lactose-free"),
         ("végétalien", "French vegan"), ("코셔", "Korean kosher"),
         ("🥜❌", "emoji no-nuts"), ("NO DAIRY!!!", "shouty caps dairy"),
         ("my kid dies if he eats sesame", "plain-english sesame"),
         ("shellfish = hospital", "plain-english shellfish"),
         ("wheat intolerance (not celiac)", "nuanced wheat"),
         ("absolutely no fish sauce", "fish sauce")]
for text, story in LANGS:
    forbid = []
    if "dairy" in text.lower() or "laktose" in text.lower():
        forbid = ["milk"]
    if "sesame" in text.lower():
        forbid = ["sesame"]
    if "shellfish" in text.lower():
        forbid = ["shellfish"]
    if "wheat" in text.lower():
        forbid = ["wheat"]
    if "fish sauce" in text.lower():
        forbid = ["fish"]
    A(P(nid(), f"Multilingual: {story}", f"writes dietary needs as '{text}'",
        req(f"ML{n}", 6 + n % 8, 70 + n % 30, 15, 600.0, "", text),
        forbid=forbid, tag="multilingual"))

# ---- 20 adversarial numerics & malformed fields
ADV = [
    (req("A1", 7, 48, 10, 99.999), 200, "float budget 99.999"),
    (req("A2", 7, 49, 10, 300.0, start_time="9:00"), 422, "start_time missing leading zero"),
    (req("A3", 7, 50, 10, 300.0, start_time="24:00"), 422, "start_time 24:00"),
    (req("A4", 7, 51, 10, 300.0, start_time="14:60"), 422, "minute 60"),
    (req("A5", 7, 52, 10, 300.0, duration_hours=0.5), 422, "duration below 1h"),
    (req("A6", 7, 53, 10, 300.0, duration_hours=9.0), 422, "duration above 8h"),
    (req("A7", 0, 54, 10, 300.0), 422, "age zero"),
    (req("A8", -3, 55, 10, 300.0), 422, "negative age"),
    (req("A9", 7, 56, 0, 300.0), 422, "zero guests"),
    (req("A10", 7, 57, -10, 300.0), 422, "negative guests"),
    (req("A11", 7, 58, 10, 0.0), 422, "zero budget"),
    (req("", 7, 59, 10, 300.0), 422, "empty name"),
    (req("A13" + "x" * 120, 7, 60, 10, 300.0), 422, "name over 100 chars"),
    (req("A14", 7, 61, 10, 300.0, theme="T" * 121), 422, "theme over limit"),
    (req("A15", 7, 62, 10, 300.0, diet="d" * 301), 422, "diet over limit"),
    (req("A16", 7, 63, 10, 300.0, special_requests="s" * 501), 422, "special requests over limit"),
    (req("A17", 7, -30, 10, 300.0), 422, "a month in the past"),
    (req("A18 null", 7, 64, 10, 300.0), 200, "null byte in name"),
    (req("A19", 7, 65, 10, 300.0, location_type="beach"), 422, "unknown location type"),
    (req("A20", 7, 66, 10, 1e308), 200, "budget 1e308"),
]
for payload, st, story in ADV:
    A(P(nid(), f"Adversary: {story}", story, payload, expect_status=st, tag="adversarial"))

# ---- 30 repeat-customer learning cohort
for i in range(30):
    A(P(nid(), f"Repeat customer {i+1}", "same hard corporate order shape, day after day",
        req(f"Repeat{i}", 7, 80 + i, 60, 1400.0, "Company Kids Day",
            "nut and dairy allergies", "venue", duration_hours=3.0),
        forbid=["peanut", "tree_nut", "milk"], tag="learning-cohort"))

# ---- 20 chaos finale
for i in range(20):
    hard_diet = ["vegan, gluten-free and sesame allergy", "kosher, nut allergy",
                 "peanut tree nut egg milk wheat soy allergies", "halal, shellfish allergy",
                 "vegetarian, soy allergy, keto"][i % 5]
    A(P(nid(), f"Chaos {i+1}", f"chaos combo {i}: {hard_diet}, odd hours, huge or tiny",
        req(f"CH{i}", [1, 7, 13, 45, 85][i % 5], 100 + i, [3, 37, 151, 320, 500][i % 5],
            [180.0, 950.0, 4200.0, 12000.0, 22000.0][i % 5], f"Chaos {i}",
            hard_diet, ["home", "park", "venue", "restaurant"][i % 4],
            start_time=["07:00", "12:15", "16:45", "20:00", "22:30"][i % 5],
            duration_hours=[1.0, 2.5, 4.0, 6.0, 8.0][i % 5],
            special_requests="accessibility; rain backup; quiet zones; parking info"),
        expect_status="flex",
        forbid={"vegan, gluten-free and sesame allergy": ["milk","egg","fish","shellfish","wheat","sesame"],
                "kosher, nut allergy": ["peanut","tree_nut"],
                "peanut tree nut egg milk wheat soy allergies": ["peanut","tree_nut","egg","milk","wheat","soy"],
                "halal, shellfish allergy": ["shellfish"],
                "vegetarian, soy allergy, keto": ["soy"]}[hard_diet],
        want_veg=any(k in hard_diet for k in ("vegan", "vegetarian", "kosher", "halal")),
        luxury=[180.0, 950.0, 4200.0, 12000.0, 22000.0][i % 5] >= 4000,
        tag="chaos"))

assert len(PERSONAS) == 150, len(PERSONAS)
if __name__ == "__main__":
    print(len(PERSONAS), "personas")
