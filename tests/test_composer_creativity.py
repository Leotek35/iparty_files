"""The Party Concept composer — creativity you can test.

Two layers:

1. Unit tests for how a request is read (band, occasion, moods, cuisines,
   tier, weighted vocabulary) and how a concept is written (headlines,
   articles, schedule).
2. The 100x coherence gate: every MECE profile plus a set of named kids/teen
   cases is composed and checked against the rules a party planner would
   apply — no cultural leakage, no characters off-palette, no adult-only acts
   for children, no alcohol for minors, a cake at birthdays, a real meal, a
   real activity, certified food where asked, budget used well, nothing
   repeated, and never a PB&J unless the host asked for one.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from iparty.llm.client import MockClient, baseline_draft, variant_for
from iparty.planning import composer as C
from iparty.planning.feasibility import KOSHER_SUPERVISION_SKU, minimum_feasible_budget
from iparty.planning.grounding import ground_draft
from iparty.planning.models import PartyRequest
from iparty.planning.prompts import build_user_prompt
from iparty.planning.verifier import verify_plan
from iparty.pricing.catalog import StaticCatalog, dietary_context

from .mece_profiles import PROFILES_MECE, build_request

CAT = StaticCatalog()
FUTURE = date.today() + timedelta(days=30)


def req(theme="", age=30, guests=20, budget=2000.0, loc="venue", diet="", name="Sam") -> PartyRequest:
    return PartyRequest(honoree_name=name, honoree_age=age, party_date=FUTURE, guest_count=guests, budget=budget,
                        theme=theme, dietary_restrictions=diet, location_type=loc)


# =============================================================== reading the request
class TestReading:
    def test_bands(self):
        assert [C.band_for(a) for a in (1, 4, 5, 8, 9, 12, 13, 17, 18, 60)] == \
            ["toddler", "toddler", "kids", "kids", "tween", "tween", "teen", "teen", "adult", "adult"]

    @pytest.mark.parametrize("theme,occasion", [
        ("Sweet 16", "sweet16"), ("Quinceañera", "quince"), ("Bar Mitzvah", "mitzvah"), ("Barn Wedding", "wedding"),
        ("Halal Engagement", "engagement"), ("Baby Shower", "baby_shower"), ("Naming Ceremony", "welcome"),
        ("Golden 50th", "birthday"), ("40th", "birthday"), ("Graduation", "graduation"), ("Retirement Tea", "retirement"),
        ("Housewarming", "housewarming"), ("Family Reunion", "reunion"), ("Diwali Night", "holiday"), ("Charity Gala", "gala"),
        ("Product Reveal", "corporate"), ("Game Night", "gathering"), ("1st Birthday", "first_birthday"),
    ])
    def test_occasions(self, theme, occasion):
        assert C.occasion_for(theme) == occasion

    def test_whole_word_matching_never_matches_inside_words(self):
        assert C.word_in("ai", "ai hackathon") and not C.word_in("ai", "kaiseki experience")
        assert "nerdy" not in C.moods_for("Kaiseki Experience") and "elegant" in C.moods_for("Kaiseki Experience")
        assert "brunch" not in C.moods_for("Crunchy Munch")

    def test_moods_and_luxury(self):
        p = C.profile_for(req("Neon Glow Dance Party", age=15, guests=30, budget=1500))
        assert {"glow"} <= p.moods and p.band == "teen"
        p = C.profile_for(req("Black Tie Gala", guests=100, budget=60000))
        assert p.luxury and p.tier == "luxury" and "elegant" in p.moods
        assert C.profile_for(req("Charity Gala", guests=250, budget=85000)).tier == "luxury"
        assert C.profile_for(req("Game Night", guests=8, budget=150, loc="home")).tier == "essential"

    def test_occasion_implied_moods(self):
        assert "elegant" in C.profile_for(req("Wedding", guests=100, budget=20000)).moods
        assert "glow" not in C.profile_for(req("Sweet 16", age=16, guests=40, budget=4000)).explicit_moods
        assert "glow" in C.profile_for(req("Sweet 16", age=16, guests=40, budget=4000)).moods

    def test_cuisines_in_order_of_mention(self):
        assert C.cuisines_for("Taco Tuesday with sushi") == ["mexican", "japanese"]
        assert C.cuisines_for("Jain Pure Veg") == ["indian"]
        assert "south_african" in C.cuisines_for("Heritage Braai")
        assert C.cuisines_for("Space Explorers") == []

    def test_birthday_inference(self):
        assert C.profile_for(req("", age=6, guests=14, budget=650, loc="home")).birthday            # blank theme on 'turning 6'
        assert C.profile_for(req("Dino Dig", age=6, guests=14, budget=650, loc="home")).birthday    # kids' themes are birthdays
        assert not C.profile_for(req("Product Reveal", guests=200, budget=50000)).birthday
        assert not C.profile_for(req("Game Night", guests=8, budget=150, loc="home")).birthday      # adults: only if they say so
        assert C.profile_for(req("Surprise 40th", age=40, guests=45, budget=5000)).birthday

    def test_dietary_needs_lifted_from_the_theme(self):
        p = C.profile_for(req("Halal Engagement", guests=40, budget=5000))
        assert "halal" in p.prefer_certs and "pork" in p.avoid
        p = C.profile_for(req("Glatt Kosher Feast", guests=40, budget=8000))
        assert "kosher" in p.prefer_certs
        p = C.profile_for(req("Vegan Brunch", guests=20, budget=1500, loc="home"))
        assert p.diet.vegetarian and p.diet.vegan and "vegan" in p.need_keys
        assert "vegetarian" in C.profile_for(req("Jain Pure Veg", guests=100, budget=9000)).need_keys


class TestVocabulary:
    def test_direct_synonym_phrase_and_hub_weights(self):
        w = C.theme_tokens("Dino Dig")
        assert w["dino"] == 1.0 and w["dig"] == 1.0 and w["fossil"] == 0.6 and w["jurassic"] == 0.6
        w = C.theme_tokens("Chamber Music")
        assert w["quartet"] == 1.0 and w["classical"] == 1.0 and w["music"] == 0.5   # a phrase is unambiguous; 'music' alone says little
        w = C.theme_tokens("Singer-songwriter night")
        assert "singer" in w and "songwriter" in w                                   # hyphenated compounds split
        assert "party" not in C.theme_tokens("Dinosaur party") and "birthday" not in C.theme_tokens("8th birthday")

    def test_item_tokens_ignore_palette_markers_and_generic_words(self):
        toks = C.item_tokens(CAT.get("ACT-DJ-TEEN"))
        assert "music" not in {t for t in toks if t == "music-fest"} and "per" not in toks and "party" not in toks
        assert "dj" in toks

    def test_theme_hits_cap_and_palette_matching(self):
        assert C.theme_hits(CAT.get("ACT-DINO-SHOW"), C.theme_tokens("Walking dinosaur show party")) == 2.0
        assert C.theme_hits(CAT.get("ACT-MAGIC"), C.theme_tokens("Dino Dig")) == 0.0
        assert C.theme_hits_palette("dino-dig", C.theme_tokens("Jurassic party"))
        assert C.theme_hits_palette("black-gold", C.theme_tokens("Sweet 16"))
        assert not C.theme_hits_palette("space", C.theme_tokens("Dino Dig"))

    def test_suggested_theme_fits_the_band_and_is_deterministic(self):
        r = req("", age=6, guests=14, budget=650, loc="home")
        assert C.suggest_theme(r) == C.suggest_theme(r) and C.suggest_theme(r) in C.SUGGESTED_THEMES["kids"]
        assert C.suggest_theme(req("", age=35, guests=20, budget=4000)) in C.ADULT_PREMIUM_THEMES
        assert C.suggest_theme(req("", age=35, guests=20, budget=600, loc="home")) in C.ADULT_THEMES


class TestWords:
    def test_headlines_drop_units_and_parentheticals(self):
        assert C.headline(CAT.get("FD-TACO-BAR")) == "Build-your-own taco bar"
        assert C.headline(CAT.get("ACT-MAGIC")) == "Magician"
        assert C.headline(CAT.get("VEN-TECH-EVENT-SPACE")) == "Tech event space"
        assert C.headline(CAT.get("ACT-LAN-SETUP")) == "LAN party setup"
        assert "(" not in C.headline(CAT.get("FD-CAKE-THEMED-2T")) and "serves" not in C.short_name(CAT.get("FD-CAKE-THEMED-2T"))

    def test_articles(self):
        assert C.with_article("Magician") == "a magician"
        assert C.with_article("Espresso cart") == "an espresso cart"
        assert C.with_article("Shawarma station") == "a shawarma station"
        assert C.with_article("Dhol players") == "dhol players"
        assert C.with_article("Live party band") == "live party band"

    def test_ordinals(self):
        assert [C._ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 40, 101)] == \
            ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "40th", "101st"]

    def test_schedule_is_monotonic_and_sane(self):
        for theme, age, budget in (("Dino Dig", 6, 650), ("Sweet 16", 16, 4000), ("Garden Brunch", 35, 2500), ("Charity Gala", 45, 60000)):
            d = C.compose(req(theme, age=age, guests=30, budget=budget, loc="home" if budget < 1000 else "venue"), CAT)
            assert d is not None
            slots = d.schedule
            assert len(slots) >= 3
            mins = [(int(s.start[:2]) * 60 + int(s.start[3:]), int(s.end[:2]) * 60 + int(s.end[3:])) for s in slots]
            assert all(a < b for a, b in mins) and all(mins[i][1] <= mins[i + 1][0] for i in range(len(mins) - 1))
            assert mins[-1][1] <= 23 * 60 + 59 and mins[0][0] >= 9 * 60


# =============================================================== composing
class TestCompose:
    def test_deterministic_and_variants_differ(self):
        r = req("Space Explorers", age=7, guests=12, budget=700, loc="home")
        a, b = C.compose(r, CAT), C.compose(r, CAT)
        assert a is not None and a.model_dump() == b.model_dump()
        cands = C.compose_candidates(r, CAT, n=3)
        assert len(cands) >= 2  # variants rotate the signature, so concepts differ

    def test_theme_drives_the_signature(self):
        d = C.compose(req("Dino Dig", age=6, guests=14, budget=900, loc="home"), CAT)
        skus = {s.sku for s in d.activities}
        assert "ACT-DINO-SHOW" in skus or "ACT-MAGIC" in skus
        d = C.compose(req("Sound Bath", age=30, guests=25, budget=2000), CAT)
        assert "ACT-SOUND-BATH" in {s.sku for s in d.activities}
        d = C.compose(req("Coffee Cupping", age=30, guests=16, budget=1200), CAT)
        assert "ACT-COFFEE-CUPPING" in {s.sku for s in d.activities}
        d = C.compose(req("Quinceañera", age=15, guests=120, budget=12000), CAT)
        assert "ACT-MARIACHI" in {s.sku for s in d.activities} and any("QUINCE" in s.sku for s in d.food)

    def test_budget_scales_the_party(self):
        lean = C.compose(req("Backyard BBQ", age=35, guests=25, budget=450, loc="home"), CAT)
        rich = C.compose(req("Backyard BBQ", age=35, guests=25, budget=4500, loc="home"), CAT)
        assert lean is not None and rich is not None
        lean_cost = ground_draft(lean, CAT, 25).total_cost
        rich_cost = ground_draft(rich, CAT, 25).total_cost
        assert lean_cost <= 450 and rich_cost <= 4500 and rich_cost > lean_cost * 3
        assert len(rich.activities) + len(rich.supplies) + len(rich.food) > len(lean.activities) + len(lean.supplies) + len(lean.food)

    def test_pbj_never_shows_up_uninvited(self):
        for theme in ("Dino Dig", "Under the Sea", "Game Night", "Backyard BBQ", ""):
            for budget in (250, 650, 2000):
                d = C.compose(req(theme, age=6, guests=14, budget=budget, loc="home"), CAT)
                assert d is None or "FD-PBJ" not in {s.sku for s in d.food}, (theme, budget)
        d = C.compose(req("Peanuts comic strip party", age=7, guests=12, budget=500, loc="home"), CAT)
        assert d is not None  # and even then the composer is free to choose something better

    def test_kosher_concept_is_certified_and_supervised(self):
        d = C.compose(req("Glatt Kosher Feast", age=40, guests=40, budget=5000), CAT)
        assert d is not None and any(s.sku == KOSHER_SUPERVISION_SKU for s in d.activities)
        for s in d.food:
            it = CAT.get(s.sku)
            assert it.course == "drink" or "kosher" in it.certifications, it.name
        assert "mashgiach" in d.notes

    def test_halal_concept_keeps_pork_and_alcohol_off(self):
        d = C.compose(req("Halal Engagement", age=30, guests=40, budget=5000), CAT)
        assert d is not None
        for s in [*d.food]:
            it = CAT.get(s.sku)
            assert "contains:pork" not in it.tags and "contains:alcohol" not in it.tags, it.name
            assert it.vegetarian or "halal" in it.certifications, it.name
        assert "halal" in d.notes.lower()

    def test_vegan_brunch_is_fully_plant_based(self):
        d = C.compose(req("Vegan Brunch", age=35, guests=20, budget=1500, loc="home"), CAT)
        assert d is not None
        diet = dietary_context(req("Vegan Brunch", age=35, guests=20, budget=1500, loc="home"))
        for s in d.food:
            assert diet.safe(CAT.get(s.sku)), CAT.get(s.sku).name

    def test_included_meal_venue_skips_the_main(self):
        d = C.compose(req("Pizza party", age=8, guests=12, budget=400, loc="restaurant"), CAT)
        assert d is not None
        venue = CAT.get(d.venue_sku)
        if "includes:main" in venue.tags:
            assert not any(CAT.get(s.sku).course == "main" for s in d.food)

    def test_unverifiable_need_yields_no_concept(self):
        assert C.compose(req("Game Night", age=30, guests=8, budget=300, loc="home", diet="keto"), CAT) is None

    def test_catalog_slice_is_relevant_and_bounded(self):
        r = req("Dino Dig", age=6, guests=14, budget=650, loc="home")
        slice_ = C.catalog_slice(r, CAT, limit=120)
        skus = {i.sku for i in slice_}
        assert len(slice_) <= 170 and "ACT-DINO-SHOW" in skus and "FD-DINO-NUGGETS" in skus
        assert all(i.min_age <= 6 <= i.max_age for i in slice_)
        assert not any("niche:adult" in i.tags or "contains:alcohol" in i.tags for i in slice_)

    def test_prompt_carries_the_verified_starting_point(self):
        r = req("Dino Dig", age=6, guests=14, budget=650, loc="home")
        base = baseline_draft(r, CAT, 0)
        text = build_user_prompt(r, CAT, baseline=base, variant=0)
        assert "VERIFIED STARTING POINT" in text and base.venue_sku in text and "concept_name" in text
        assert "a child" in text

    def test_variant_mapping_and_mock_serves_the_concept(self):
        assert [variant_for(t) for t in (0.4, 0.55, 0.7, 0.85)] == [0, 1, 2, 3]
        import asyncio
        r = req("Dino Dig", age=6, guests=14, budget=650, loc="home")
        d0 = asyncio.run(MockClient(flaw_rate=0.0).generate_draft(r, CAT, temperature=0.4))
        assert d0.model_dump() == C.compose(r, CAT).model_dump()
        d1 = asyncio.run(MockClient(flaw_rate=0.0).generate_draft(r, CAT, temperature=0.55))
        assert d1.model_dump() == baseline_draft(r, CAT, 1).model_dump()
        flawed = asyncio.run(MockClient(flaw_rate=1.0).generate_draft(r, CAT, temperature=0.4))
        assert not verify_plan(ground_draft(flawed, CAT, 14), r, CAT).passed


# =============================================================== the 100x coherence gate
NAMED_CASES = [
    ("Laser Tag", 30, 36, 4000, "venue", ""), ("Pottery Studio", 30, 12, 1500, "venue", ""), ("Chamber Music", 30, 22, 2400, "venue", ""),
    ("Coffee Cupping", 30, 16, 1200, "venue", ""), ("Escape Puzzle", 30, 28, 3200, "venue", ""), ("Sound Bath", 30, 25, 2000, "venue", ""),
    ("Kaiseki Experience", 30, 14, 4800, "venue", ""), ("Glatt Kosher Feast", 40, 40, 5000, "venue", ""), ("Halal Engagement", 30, 40, 5000, "venue", ""),
    ("Vegan Brunch", 35, 20, 1500, "home", ""), ("Bar Mitzvah", 13, 60, 8000, "venue", ""), ("Diwali Night", 30, 60, 8000, "venue", ""),
    ("Eid al-Fitr", 30, 60, 2500, "venue", "halal"), ("", 6, 14, 650, "home", ""), ("", 45, 20, 2000, "home", ""), ("", 2, 12, 600, "home", ""),
    ("Under the Sea", 6, 14, 650, "home", "nut allergy"), ("Backyard Cookout", 40, 30, 4500, "home", ""), ("Sweet 16", 16, 40, 4000, "venue", ""),
    ("Quinceañera", 15, 120, 12000, "venue", ""), ("Dino Dig", 6, 15, 600, "home", "gluten free"), ("Game Night", 30, 8, 150, "home", ""),
    ("Peanuts comic strip party", 7, 12, 500, "home", ""), ("Movie Night", 9, 14, 320, "home", ""), ("Baby shower", 30, 20, 300, "home", ""),
    ("Space Explorers", 7, 16, 900, "park", ""), ("Princess Tea Party", 5, 10, 500, "home", ""), ("Superhero Training", 6, 12, 700, "venue", ""),
    ("Spa Day", 11, 8, 400, "home", ""), ("Minecraft Build", 9, 12, 550, "home", ""), ("Neon Glow", 14, 25, 1200, "venue", ""),
    ("Taco Fiesta", 38, 30, 1800, "home", "no pork"), ("Garden Brunch", 60, 24, 2200, "venue", "vegetarian"), ("Retirement Party", 65, 40, 3000, "restaurant", ""),
    ("Soccer Party", 8, 14, 500, "park", ""), ("Carnival", 7, 40, 2500, "park", ""), ("Winter Wonderland", 5, 12, 650, "home", "dairy free"),
]


def _profile_requests():
    out = []
    for p in PROFILES_MECE:
        if p["expect"] not in ("pass", "pass_sanitized"):
            continue
        out.append((p["id"], build_request(p)))
    for i, (theme, age, g, b, loc, diet) in enumerate(NAMED_CASES):
        out.append((f"N{i:02d}-{theme or 'blank'}", req(theme, age=age, guests=g, budget=b, loc=loc, diet=diet)))
    return out


MATRIX = _profile_requests()


def _audit(r: PartyRequest) -> list[str]:
    """Every rule a party planner would apply to a concept, as a list of findings."""
    findings: list[str] = []
    p = C.profile_for(r, theme=r.theme if r.theme.strip() else C.suggest_theme(r, 0))  # the composer's own reading
    d = C.compose(r, CAT)
    if d is None:
        floor = minimum_feasible_budget(r, CAT)
        if floor is not None and floor <= r.budget and not p.diet.unverifiable:
            findings.append(f"no concept although the floor ${floor} fits the budget")
        return findings
    plan = ground_draft(d, CAT, r.guest_count)
    report = verify_plan(plan, r, CAT)
    if not report.passed:
        findings.append("does not verify: " + ", ".join(v.code for v in report.violations if v.severity == "error"))
    if plan.total_cost > r.budget + 0.01:
        findings.append("over budget")
    if p.tier in ("standard", "premium", "luxury") and plan.total_cost < 0.5 * r.budget:
        findings.append(f"uses only {plan.total_cost / r.budget:.0%} of the budget")
    skus = [d.venue_sku, *(s.sku for s in d.food), *(s.sku for s in d.supplies), *(s.sku for s in d.activities)]
    if len(skus) != len(set(skus)):
        findings.append("repeats an item")
    if not d.concept_name or not d.story or len(d.moments) < 2:
        findings.append("thin concept (name/story/moments)")
    if "(per person)" in d.story or "(serves" in d.story or "  " in d.story or not d.story.endswith("."):
        findings.append("story copy not clean")
    items = [CAT.get(s) for s in skus]
    venue = CAT.get(d.venue_sku)
    if r.location_type not in venue.location_types or not venue.within_capacity(r.guest_count):
        findings.append("venue does not fit the place or the headcount")
    if not any(it.category == "activities" and not it.is_service for it in items):
        findings.append("no real activity")
    feeds = "includes:main" in venue.tags
    mains = sum(it.servings_for(next(s.quantity for s in d.food if s.sku == it.sku), r.guest_count) for it in items if it.category == "food" and it.course == "main")
    if not feeds and mains < r.guest_count:
        findings.append("main course does not cover the guests")
    if (p.birthday or p.occasion in ("sweet16", "quince", "first_birthday")) and not any(it.course == "cake" for it in items):
        findings.append("birthday without a cake")
    for it in items:
        tags = it.tags
        hits = C.theme_hits(it, p.words)
        cuisines = C._cuisine_tags(it)
        specific = [c for c in cuisines if c in C.SPECIFIC_CUISINES]
        if specific and not any(c in p.cuisines for c in cuisines):
            if it.category != "food":
                findings.append(f"cultural leakage: {it.name}")
            elif hits < 1.6:
                findings.append(f"cuisine leakage: {it.name}")
        if "niche:adult" in tags and (p.band != "adult" or hits < 1.0):
            findings.append(f"adult-only act without being asked: {it.name}")
        if "niche" in tags and hits < 1.0 and not any(c in p.cuisines for c in cuisines):
            findings.append(f"niche item without a theme hit: {it.name}")
        needs = [t[6:] for t in tags if t.startswith("needs:")]
        if needs and not any(C.need_in(n, p.text) for n in needs):
            findings.append(f"occasion-specific item for the wrong occasion: {it.name}")
        if "style:character" in tags and hits < 1.0 and not any(C.theme_hits_palette(t[6:], p.words) for t in tags if t.startswith("theme:")):
            findings.append(f"character off-palette: {it.name}")
        if it.category == "supplies" and any(t.startswith("theme:") for t in tags) and hits < 1.0 and not any(
                C.theme_hits_palette(t[6:], p.words) for t in tags if t.startswith("theme:")):
            findings.append(f"themed product off-palette: {it.name}")
        if "contains:alcohol" in tags and r.honoree_age < 21:
            findings.append(f"alcohol for a minor: {it.name}")
        if not C.segment_ok(it, p.band):
            findings.append(f"wrong segment: {it.name}")
        if not (it.min_age <= r.honoree_age <= it.max_age):
            findings.append(f"age-inappropriate: {it.name}")
        if it.sku == "FD-PBJ" and "peanut" not in p.text and "pb&j" not in p.text:
            findings.append("PB&J without being asked")
    diet = p.diet
    for it in items:
        if it.category == "food" and not diet.safe(it):
            findings.append(f"unsafe for the dietary picture: {it.name}")
    return findings


@pytest.mark.parametrize("pid,r", MATRIX, ids=[pid for pid, _ in MATRIX])
def test_every_profile_gets_a_coherent_concept(pid, r):
    findings = _audit(r)
    assert not findings, f"{pid} {r.theme!r}: " + "; ".join(findings)


def test_the_matrix_is_broad():
    assert len(MATRIX) >= 120
    bands = {C.band_for(r.honoree_age) for _, r in MATRIX}
    assert bands == {"toddler", "kids", "tween", "teen", "adult"}


def test_concepts_are_varied_across_the_matrix():
    """A creative engine must not hand everyone the same party: across the
    matrix the signature acts and the mains should be plentiful."""
    sigs, mains, names = set(), set(), set()
    for _, r in MATRIX:
        d = C.compose(r, CAT)
        if d is None:
            continue
        names.add(d.concept_name)
        acts = [CAT.get(s.sku) for s in d.activities]
        if acts:
            sigs.add(acts[0].sku)
        for s in d.food:
            if CAT.get(s.sku).course == "main":
                mains.add(s.sku)
    assert len(sigs) >= 35, len(sigs)
    assert len(mains) >= 25, len(mains)
    assert len(names) >= len(MATRIX) * 0.85


def test_variants_change_the_concept_for_most_parties():
    changed = 0
    for _, r in MATRIX[:60]:
        a, b = C.compose(r, CAT, 0), C.compose(r, CAT, 1)
        if a is not None and b is not None and a.model_dump() != b.model_dump():
            changed += 1
    assert changed >= 30, changed
