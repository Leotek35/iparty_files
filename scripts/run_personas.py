"""Run all 100 personas against the live app; emit per-user feedback + aggregate report."""
from __future__ import annotations
import collections
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi.testclient import TestClient  # noqa: E402

from iparty.api.app import app  # noqa: E402
from personas import PERSONAS  # noqa: E402

# Features the CURRENT product supports (update as we ship improvements).
# v1.1: time window, special-requests channel, diet mappings, new catalog SKUs.
SUPPORTED_FEATURES: set[str] = {
    "custom_start_time", "custom_duration",             # real request fields
    "kosher", "halal", "pescatarian", "jain",           # honored via vegetarian mapping + note
    "baby_safe", "teen_activities", "dj", "photo_booth", "adult_theme",
    "stem_kits", "eco_supplies", "character_performer", "catering_upgrade",  # new SKUs
    # expressible via special_requests, echoed to the coordinator in plan notes:
    "accessibility", "weather_backup", "quiet_activities", "av_equipment",
    "parking_info", "surprise_mode", "bilingual", "music_playlist",
    "custom_decor", "soft_food", "cultural_traditions", "lifeguard", "invitations",
}
# needs users can now express through the special_requests field
SPECIAL_VIA_TEXT = {
    "accessibility", "weather_backup", "quiet_activities", "av_equipment",
    "parking_info", "surprise_mode", "bilingual", "music_playlist",
    "custom_decor", "soft_food", "cultural_traditions", "lifeguard", "invitations",
}

client = TestClient(app)
results, feedback_items = [], []

for p in PERSONAS:
    payload = dict(p["payload"])
    feats = set(p["want_features"])
    if "custom_start_time" in feats:
        payload["start_time"] = "18:00"
    if "custom_duration" in feats:
        payload["duration_hours"] = 4.0
    wanted_special = [f for f in feats if f in SPECIAL_VIA_TEXT]
    if wanted_special:
        payload["special_requests"] = "; ".join(f.replace("_", " ") for f in wanted_special)
    p = {**p, "payload": payload}
    r = client.post("/api/v1/plan", json=payload)
    fb = []  # (severity, code, message)
    entry = {"id": p["id"], "name": p["name"], "tag": p["tag"], "status": r.status_code}

    if p["expect_status"] != 200:
        if r.status_code == p["expect_status"]:
            fb.append(("praise", "GRACEFUL_REJECTION", "App refused impossible/invalid request clearly."))
            if r.status_code == 409:
                det = r.json().get("detail", {})
                if det.get("minimum_feasible_budget"):
                    fb.append(("praise", "MIN_BUDGET_SHOWN", f"Told me the minimum budget: ${det['minimum_feasible_budget']}"))
        else:
            fb.append(("blocker", "WRONG_STATUS", f"Expected {p['expect_status']}, got {r.status_code}: {r.text[:150]}"))
    elif r.status_code != 200:
        guided = r.status_code == 409 and (r.json().get("detail") or {}).get("minimum_feasible_budget")
        if guided:
            fb.append(("minor", "REFUSED_WITH_GUIDANCE",
                       f"No plan possible at ${p['payload']['budget']}, but app told me the minimum (${guided})"))
        else:
            fb.append(("blocker", "PLAN_REFUSED", f"Expected a plan, got {r.status_code}: {r.text[:200]}"))
    else:
        body = r.json()
        plan, verif = body["plan"], body["verification"]
        total = plan["total_cost"]
        budget = p["payload"]["budget"]
        guests = p["payload"]["guest_count"]
        # hard checks
        if total > budget + 0.01:
            fb.append(("blocker", "OVER_BUDGET", f"Plan ${total} > budget ${budget}"))
        menu = plan["menu"]
        servings = sum(m["servings"] for m in menu)
        if servings < guests:
            fb.append(("blocker", "UNDERFED", f"{servings} servings for {guests} guests"))
        for a in p["forbid_allergens"]:
            bad = [m["name"] for m in menu if a in m["allergens"]]
            if bad:
                fb.append(("blocker", "ALLERGEN_UNSAFE", f"{a} present in: {', '.join(bad)}"))
        if p["want_vegetarian"]:
            vs = sum(m["servings"] for m in menu if m["vegetarian"])
            if vs < guests:
                fb.append(("blocker", "NOT_VEGETARIAN", f"only {vs} veg servings for {guests}"))
        # delight checks
        util = total / budget if budget else 0
        if p["luxury"] and util < 0.35:
            ack = "premium vendors" in plan.get("notes", "")
            fb.append(("minor" if ack else "major", "BUDGET_UNDERUSED" + ("_ACKNOWLEDGED" if ack else ""),
                       f"plan spends ${total} of ${budget} ({util:.0%})" + (" — but app was upfront about catalog limits" if ack else " — feels cheap, not premium")))
        warns = [v["code"] for v in verif["violations"]]
        if "BUDGET_SUSPICIOUSLY_LOW" in warns and not p["luxury"]:
            fb.append(("minor", "LOW_SPEND_WARNING", "app itself flags plan may be incomplete"))
        acts = plan["activities"]
        if len(acts) <= 1 and budget >= 1000:
            fb.append(("major", "THIN_ACTIVITIES", f"only {len(acts)} activity for a ${budget} party"))
        if p["payload"]["theme"] and p["payload"]["theme"].lower() not in json.dumps(plan, ensure_ascii=False).lower():
            fb.append(("minor", "THEME_IGNORED", f"asked for '{p['payload']['theme']}' theme, not reflected"))
        # dietary comprehension: did app act on the restriction at all?
        diet = p["payload"]["dietary_restrictions"]
        if diet and not p["forbid_allergens"] and not p["want_vegetarian"] and p["tag"] == "unmapped-diet":
            note_blob = (plan.get("notes","") + json.dumps(verif)).lower()
            first = diet.lower().replace(",", " ").split()[0]
            if first not in note_blob:
                fb.append(("major", "DIET_SILENTLY_IGNORED", f"'{diet}' neither honored nor acknowledged — dangerous silence"))
        # honored-feature spot checks
        if payload.get("start_time") == "18:00" and plan["schedule"]:
            if plan["schedule"][0]["start"] < "18:00":
                fb.append(("major", "START_TIME_IGNORED", "asked for 6pm, schedule starts earlier"))
        if payload.get("special_requests"):
            if payload["special_requests"].split(";")[0].strip() not in plan.get("notes", ""):
                fb.append(("major", "SPECIAL_REQUEST_DROPPED", "special requests not acknowledged in plan"))
    # unmet feature desires
    for f in p["want_features"]:
        if f not in SUPPORTED_FEATURES:
            fb.append(("major", f"MISSING_FEATURE:{f}", f"Needed '{f}', app has no way to express it"))
    if not fb:
        fb.append(("praise", "DELIGHTED", "Everything I needed, verified and on budget."))
    entry["feedback"] = fb
    results.append(entry)
    for sev, code, msg in fb:
        feedback_items.append({"persona": p["id"], "tag": p["tag"], "severity": sev, "code": code, "msg": msg})

# aggregate
sev_rank = {"blocker": 0, "major": 1, "minor": 2, "praise": 3}
agg = collections.Counter((f["severity"], f["code"].split(":")[0] if ":" not in f["code"] else f["code"]) for f in feedback_items)
delighted = sum(1 for e in results if all(s == "praise" for s, *_ in e["feedback"]))
blocked = sum(1 for e in results if any(s == "blocker" for s, *_ in e["feedback"]))
majored = sum(1 for e in results if any(s == "major" for s, *_ in e["feedback"]))
print(f"personas: 100 | delighted: {delighted} | with blockers: {blocked} | with major issues: {majored}")
print("\n--- issue frequency ---")
for (sev, code), n in sorted(agg.items(), key=lambda kv: (sev_rank[kv[0][0]], -kv[1])):
    print(f"{sev:8s} {code:35s} x{n}")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona_results.json")
json.dump(results, open(out, "w"), indent=1)
print("\nwrote", out)
