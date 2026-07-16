"""100 synthetic customer profiles with mutually exclusive, maximally complex needs.

Each persona: identity + backstory, an API payload, and machine-checkable
expectations. `want_features` lists desires the current product may not support;
every unmet one becomes structured feedback.
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

# ---- 1-12: single-allergen parents, one per FDA big-9 + variants (mutually exclusive allergens)
for i, (kw, allerg, nm) in enumerate([
    ("peanut allergy", ["peanut"], "Priya"), ("tree nut allergy", ["tree_nut"], "Tomas"),
    ("milk allergy", ["milk"], "Dana"), ("egg allergy", ["egg"], "Elif"),
    ("soy allergy", ["soy"], "Sofia"), ("wheat allergy", ["wheat"], "Wanda"),
    ("fish allergy", ["fish"], "Finn"), ("shellfish allergy", ["shellfish"], "Shelly"),
    ("sesame allergy", ["sesame"], "Sam"), ("celiac disease", ["wheat"], "Celia"),
    ("lactose intolerant guests", ["milk"], "Lars"), ("gluten-free household", ["wheat"], "Grete")], 1):
    A(P(f"p{i:03d}", f"{nm} (parent)", f"Parent whose child has {kw}; terrified of cross-contamination; wants explicit safety confirmation.",
        req(f"Kid{i}", 5 + i % 7, 20 + i, 10 + i, 400 + 20 * i, "Dinosaurs", kw, ["home", "park", "venue", "restaurant"][i % 4]),
        forbid=allerg, tag="allergy"))

# ---- 13-20: multi-allergen & diet stacking (each combo unique)
combos = [
    ("vegan", ["milk", "egg", "fish", "shellfish"], True, "Vera"),
    ("vegetarian", [], True, "Vik"),
    ("vegan and gluten-free", ["milk", "egg", "fish", "shellfish", "wheat"], True, "Veda"),
    ("nut allergy and dairy-free", ["peanut", "tree_nut", "milk"], False, "Nadia"),
    ("egg and soy and sesame allergies", ["egg", "soy", "sesame"], False, "Esme"),
    ("gluten-free and vegetarian", ["wheat"], True, "Gia"),
    ("shellfish and fish allergies, vegetarian preferred", ["shellfish", "fish"], True, "Sasha"),
    ("peanut, tree nut, egg, milk, wheat, soy, fish, shellfish and sesame allergies", 
     ["peanut", "tree_nut", "egg", "milk", "wheat", "soy", "fish", "shellfish", "sesame"], False, "Max"),
]
for j, (diet, allerg, veg, nm) in enumerate(combos, 13):
    A(P(f"p{j:03d}", f"{nm} (diet-stacker)", f"Needs '{diet}' for the whole party; will read every label.",
        req(f"Child{j}", 4 + j % 9, 15 + j, 8 + j, 500 + 30 * j, "Space Explorers", diet),
        forbid=allerg, want_veg=veg, tag="diet-combo"))

# ---- 21-28: religious/lifestyle diets the parser may not know (each different)
for j, (diet, nm, feat) in enumerate([
    ("kosher", "Rivka", "kosher"), ("halal", "Hassan", "halal"),
    ("hindu vegetarian, no egg", "Anand", None), ("jain — no root vegetables, vegetarian", "Jaya", "jain"),
    ("pescatarian", "Pearl", "pescatarian"), ("keto, low carb only", "Kai", "keto"),
    ("diabetic child — low sugar menu", "Dee", "low_sugar"), ("paleo", "Pat", "paleo")], 21):
    feats = [feat] if feat else []
    veg = "vegetarian" in diet
    A(P(f"p{j:03d}", f"{nm}", f"Family strictly follows '{diet}'; unlabeled food is a dealbreaker.",
        req(f"Kid{j}", 6 + j % 6, 10 + j, 12 + j % 20, 450 + 25 * j, "", diet),
        want_veg=veg, want_features=feats, tag="unmapped-diet"))

# ---- 29-40: age extremes (each age bracket exclusive)
ages = [(1, "first birthday, needs baby-safe activities", ["baby_safe"]),
        (2, "toddler; no small parts, nap-time scheduling", ["custom_start_time"]),
        (13, "teen who finds bounce houses embarrassing", ["teen_activities"]),
        (16, "sweet sixteen, wants DJ and photo booth", ["dj", "photo_booth"]),
        (18, "18th, wants casino-night theme", ["adult_theme"]),
        (21, "21st, wants cocktail bar", ["alcohol_service"]),
        (30, "30th, ironic kids-party theme", []),
        (40, "40th, wine tasting", ["alcohol_service", "catering_upgrade"]),
        (65, "retirement-age, garden party, accessible seating", ["accessibility"]),
        (75, "75th, large-print invitations, quiet music", ["accessibility", "invitations"]),
        (90, "90th, wheelchair access, soft food menu", ["accessibility", "soft_food"]),
        (100, "100th birthday! Press may attend", ["accessibility"])]
for j, (age, story, feats) in enumerate(ages, 29):
    A(P(f"p{j:03d}", f"Age-{age} organizer", story,
        req(f"Honoree{age}", age, 30 + j, 15 + j % 30, 700 + 10 * j, "", "", ["home", "venue", "restaurant"][j % 3]),
        want_features=feats, tag="age-extreme"))

# ---- 41-48: budget extremes (mutually exclusive brackets)
budgets = [(15.0, 4, 409, "single parent, $15 hard cap"), (40.0, 8, None, "college student, $40"),
           (80.0, 12, None, "tight but hopeful, $80"), (2500.0, 20, None, "wants premium everything"),
           (10000.0, 30, None, "luxury planner: 'money is no object'"),
           (25000.0, 60, None, "corporate family day, expects vendors"),
           (0.01, 5, 409, "tests the system with 1 cent"), (150.0, 150, 409, "$1/head for 150 guests")]
for j, (b, g, st, story) in enumerate(budgets, 41):
    A(P(f"p{j:03d}", f"Budget-{b:g} customer", story,
        req(f"Kid{j}", 7, 25 + j, g, b), expect_status=st or 200,
        luxury=b >= 2500, tag="budget-extreme"))

# ---- 49-56: guest-count extremes
guests = [(1, "just the two of us"), (2, "twins + one friend... wait, 2 guests total"),
          (45, "whole class plus siblings"), (120, "big family reunion birthday"),
          (250, "community block party"), (400, "school-wide event"),
          (500, "max capacity stress test"), (3, "micro-party, quality over quantity")]
for j, (g, story) in enumerate(guests, 49):
    A(P(f"p{j:03d}", f"{g}-guest host", story,
        req(f"Kid{j}", 8, 20 + j, g, max(200.0, g * 12.0), "", "", "park" if g > 100 else "home"),
        tag="guest-extreme"))

# ---- 57-64: location & logistics seekers (each wants a different unsupported thing)
for j, (loc, story, feats) in enumerate([
    ("park", "outdoor party but monsoon season — needs a rain backup plan", ["weather_backup"]),
    ("venue", "needs wheelchair-accessible venue confirmation", ["accessibility"]),
    ("home", "apartment; needs low-noise activities only", ["quiet_activities"]),
    ("restaurant", "private room for 30 with AV for slideshow", ["av_equipment"]),
    ("park", "two permits? wants beach location, app has no 'beach'", ["beach_location"]),
    ("venue", "wants venue suggestions with real addresses", ["venue_directory"]),
    ("home", "backyard pool party — safety supervision", ["lifeguard"]),
    ("restaurant", "needs parking validation for 20 cars", ["parking_info"])], 57):
    A(P(f"p{j:03d}", f"Logistics-{j}", story,
        req(f"Kid{j}", 9, 35 + j, 18 + j, 900.0, "", "", loc),
        want_features=feats, tag="logistics"))

# ---- 65-72: scheduling demanders (all want time control the app lacks)
for j, (story, feats) in enumerate([
    ("evening party 6-9pm; default 2pm slot useless", ["custom_start_time"]),
    ("brunch birthday 10am", ["custom_start_time"]),
    ("4-hour marathon party", ["custom_duration"]),
    ("90-minute express party", ["custom_duration"]),
    ("needs itinerary emailed to guests", ["email_invites"]),
    ("multi-day quinceañera weekend", ["multi_day"]),
    ("surprise party — schedule must hide honoree arrival", ["surprise_mode"]),
    ("shared party for twins with different interests", ["multi_honoree"])], 65):
    A(P(f"p{j:03d}", f"Scheduler-{j}", story,
        req(f"Kid{j}", 10, 40 + j, 16, 800.0, ["Superheroes", "Under the Sea"][j % 2]),
        want_features=feats, tag="scheduling"))

# ---- 73-80: theme & culture seekers
for j, (theme, story, feats) in enumerate([
    ("Quinceañera", "traditional quinceañera elements", ["cultural_traditions"]),
    ("Lunar New Year Dragon", "bilingual Mandarin/English party", ["bilingual"]),
    ("Bollywood", "specific music & dance floor", ["music_playlist"]),
    ("Minecraft", "licensed characters worry — is this legal?", ["licensed_themes"]),
    ("Frozen princess", "character performer visit", ["character_performer"]),
    ("Science lab", "STEM experiments, safety goggles for 25", ["stem_kits"]),
    ("Eco-friendly zero waste", "no plastic; compostable everything", ["eco_supplies"]),
    ("Goth teen", "black balloons only, absolutely no rainbows", ["custom_decor"])], 73):
    A(P(f"p{j:03d}", f"Theme-{j}", story,
        req(f"Kid{j}", 7 + j % 10, 45 + j, 20 + j, 1100.0, theme),
        want_features=feats, tag="theme"))

# ---- 81-90: hostile/edge inputs (each attacks a different field)
edge = [
    (req("A" * 100, 7, 50, 10, 300.0), 200, "100-char name at the limit"),
    (req("Zoeé✨🎂", 6, 51, 10, 300.0), 200, "emoji + accents in name"),
    (req("Robert'); DROP TABLE plans;--", 8, 52, 10, 300.0), 200, "SQL injection name"),
    (req("<script>alert(1)</script>", 9, 53, 10, 300.0), 200, "XSS attempt in name"),
    (req("Kid", 121, 54, 10, 300.0), 422, "age 121 over limit"),
    (req("Kid", 7, -5, 10, 300.0), 422, "party date in the past"),
    (req("Kid", 7, 55, 501, 6000.0), 422, "501 guests over limit"),
    (req("Kid", 7, 56, 10, -50.0), 422, "negative budget"),
    (req("Kid", 7, 57, 10, 300.0, diet="x" * 300), 200, "300-char dietary string at limit"),
    (req("Kid", 7, 0, 10, 300.0), 200, "party TODAY, zero lead time"),
]
for j, (payload, st, story) in enumerate(edge, 81):
    A(P(f"p{j:03d}", f"Edge-{j}", story, payload, expect_status=st, tag="edge-input"))

# ---- 91-100: contradiction & stress personas
A(P("p091", "Contradictor", "wants vegan party BUT insists on the regular birthday cake by name",
    req("Ivy", 6, 60, 12, 500.0, "", "vegan"), forbid=["milk", "egg", "fish", "shellfish"], want_veg=True, tag="contradiction"))
A(P("p092", "Penny-luxe", "luxury expectations on a $100 budget for 40 guests", req("Lux", 7, 61, 40, 100.0),
    expect_status=409, tag="contradiction"))
A(P("p093", "All-allergy vegan", "vegan PLUS all nine allergens excluded — near-impossible menu",
    req("Ori", 5, 62, 10, 800.0, "", "vegan, peanut, tree nut, wheat, soy, sesame allergies"),
    forbid=["milk", "egg", "fish", "shellfish", "peanut", "tree_nut", "wheat", "soy", "sesame"], want_veg=True, tag="contradiction"))
A(P("p094", "1-year-old rager", "wants a bounce house AND magician for a 1-year-old",
    req("Bub", 1, 63, 20, 1500.0, "Circus"), tag="contradiction"))
A(P("p095", "Adult bounce", "45-year-old who explicitly wants a bounce house (max_age 12)",
    req("Rex", 45, 64, 25, 2000.0, "Nostalgia"), want_features=["adult_bounce_house"], tag="contradiction"))
A(P("p096", "Restaurant misfit", "500 guests at a restaurant (per-person venue = $11k floor)",
    req("Gala", 50, 65, 500, 5000.0, "", "", "restaurant"), expect_status=409, tag="contradiction"))
A(P("p097", "Zero-notice bulk", "party today for 300 with every allergen excluded",
    req("Rush", 8, 0, 300, 3000.0, "", "peanut tree nut egg milk wheat soy sesame allergies"),
    forbid=["peanut", "tree_nut", "egg", "milk", "wheat", "soy", "sesame"], tag="contradiction"))
A(P("p098", "Data hoarder", "wants plan exported as PDF + calendar invites", req("Doc", 9, 66, 15, 600.0),
    want_features=["pdf_export", "calendar_export"], tag="feature-seeker"))
A(P("p099", "Comparison shopper", "wants THREE plan options side by side to choose from",
    req("Trio", 10, 67, 18, 900.0), want_features=["multiple_options"], tag="feature-seeker"))
A(P("p100", "Skeptic", "doesn't trust totals; wants line-item receipts with vendor names",
    req("Audra", 11, 68, 22, 1200.0), want_features=["vendor_names"], tag="feature-seeker"))

assert len(PERSONAS) == 100, len(PERSONAS)
if __name__ == "__main__":
    print(len(PERSONAS), "personas")
