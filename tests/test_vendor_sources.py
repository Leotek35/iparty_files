"""Vendor sources — real listings near the host, without ever trusting them
for prices. Every source is exercised with recorded fixtures (no network),
including outages, and the vendor-onboarded catalog merge."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from iparty.api.app import create_app
from iparty.pricing.catalog import StaticCatalog
from iparty.pricing.vendors import (
    FoursquareSource,
    GooglePlacesSource,
    OverpassSource,
    VendorDirectory,
    YelpSource,
    load_vendor_items,
    marketplace_links,
    vendor_query,
)

CAT = StaticCatalog()


def _fetch_with(payloads: dict[str, object]):
    """A fake HTTP layer keyed by endpoint substring; records calls."""
    calls: list[tuple[str, dict, dict | None]] = []

    def fetch(url, params, headers=None, json_body=None):
        calls.append((url, params, json_body))
        for key, payload in payloads.items():
            if key in url:
                return payload
        return None
    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


# ---------------------------------------------------------------- queries & links
def test_vendor_query_is_specific_and_certification_aware():
    assert vendor_query(CAT.get("ACT-MAGIC")) == "kids party magician"
    assert "halal" in vendor_query(CAT.get("FD-BIRYANI"))
    assert "kosher" in vendor_query(CAT.get("FD-KOSHER-BUFFET"))
    assert "thai" in vendor_query(CAT.get("FD-THAI-BUFFET"))
    assert vendor_query(CAT.get("SUP-TENT")) == "tent rental"


def test_marketplace_links_need_no_keys_and_encode_the_place():
    links = marketplace_links(CAT.get("ACT-DJ-PRO"), "Austin, TX")
    sources = {ln["source"] for ln in links}
    assert {"Yelp", "Thumbtack", "GigSalad"} <= sources
    assert all("Austin" in ln["url"] or ln["source"] == "The Bash" for ln in links)
    assert "Peerspace" in {ln["source"] for ln in marketplace_links(CAT.get("VEN-LOFT"), "Denver")}


# ---------------------------------------------------------------- sources
def test_google_places_source_parses_and_caches():
    fetch = _fetch_with({"places.googleapis.com": {"places": [
        {"id": "ChIJ1", "displayName": {"text": "Magic Mike's Shows"}, "formattedAddress": "1 Main St, Austin, TX",
         "rating": 4.8, "userRatingCount": 120, "priceLevel": "PRICE_LEVEL_MODERATE", "googleMapsUri": "https://maps.google.com/?cid=1"}]}})
    src = GooglePlacesSource("test-key", fetch)
    found = src.search("kids party magician", "Austin, TX", 5)
    assert len(found) == 1 and found[0].name == "Magic Mike's Shows" and found[0].rating == 4.8
    assert found[0].external_id == "ChIJ1" and found[0].source == "google_places"
    # the API key travels in a header, never in the URL; the field mask is the Pro set
    url, params, body = fetch.calls[0]
    assert "key" not in params and body["textQuery"].startswith("kids party magician")
    src.search("kids party magician", "Austin, TX", 5)
    assert len(fetch.calls) == 1  # cached


def test_yelp_source_parses_distance_and_price():
    fetch = _fetch_with({"api.yelp.com": {"businesses": [
        {"id": "y1", "name": "Bounce Kingdom", "rating": 4.5, "review_count": 88, "price": "$$", "url": "https://yelp.com/biz/bk",
         "distance": 1234.5, "location": {"display_address": ["2 Oak Ave", "Austin, TX 78701"]}}]}})
    found = YelpSource("k", fetch).search("bounce house rental", "Austin, TX", 3)
    assert found[0].distance_m == 1234 and found[0].price_level == "$$" and "Oak Ave" in found[0].address


def test_foursquare_source_parses():
    fetch = _fetch_with({"api.foursquare.com": {"results": [
        {"fsq_id": "f1", "name": "Taco Truck Co", "distance": 800, "location": {"formatted_address": "3 Pine St"}}]}})
    found = FoursquareSource("k", fetch).search("taco catering", "Austin", 3)
    assert found[0].name == "Taco Truck Co" and found[0].url.endswith("/v/f1")


def test_overpass_fallback_geocodes_then_lists_named_places():
    fetch = _fetch_with({
        "nominatim": [{"lat": "30.27", "lon": "-97.74"}],
        "overpass": {"elements": [
            {"type": "node", "id": 5, "tags": {"name": "Sweet Crumbs Bakery", "addr:street": "Elm St", "website": "https://sc.example"}},
            {"type": "node", "id": 6, "tags": {}}]},
    })
    found = OverpassSource(fetch).search("custom cakes bakery", "Austin, TX", 5)
    assert len(found) == 1 and found[0].name == "Sweet Crumbs Bakery" and found[0].external_id == "node/5"
    assert "bakery" in fetch.calls[1][1]["data"]


def test_directory_falls_through_outages_and_always_keeps_links():
    boom = GooglePlacesSource("k", _fetch_with({}))     # empty answer (outage / nothing found)
    yelp = YelpSource("k", _fetch_with({"api.yelp.com": {"businesses": [{"id": "y", "name": "Plan B DJ", "rating": 5.0}]}}))
    d = VendorDirectory([boom, yelp])
    result = d.lookup(CAT.get("ACT-DJ-PRO"), "Austin, TX")
    assert result["source"] == "yelp" and result["listings"][0]["name"] == "Plan B DJ"
    assert result["links"] and "note" in result

    class Raising:
        name = "raising"

        def search(self, *a, **k):
            raise RuntimeError("down")
    result = VendorDirectory([Raising()]).lookup(CAT.get("ACT-DJ-PRO"), "Austin, TX")
    assert result["source"] is None and result["listings"] == [] and result["links"]


def test_directory_from_settings_is_empty_without_keys():
    assert VendorDirectory.from_settings().configured() == []


# ---------------------------------------------------------------- onboarded rows
def test_vendor_rows_merge_into_the_catalog_as_quotes(tmp_path):
    path = tmp_path / "vendor_catalog.jsonl"
    rows = [
        {"sku": "VND-SWEETCRUMBS-CAKE", "category": "food", "subcategory": "cake", "name": "Sweet Crumbs two-tier cake (serves 30)",
         "unit": "flat", "unit_price": 140.0, "serves": 30, "allergens": ["wheat", "egg", "milk"], "vegetarian": True,
         "min_age": 0, "max_age": 120, "location_types": ["home", "venue", "park", "restaurant"], "tier": "standard",
         "tags": ["seg:all", "signature"], "status": "approved"},
        {"sku": "VND-PENDING", "category": "food", "subcategory": "cake", "name": "Pending", "unit": "flat", "unit_price": 1,
         "serves": 1, "status": "pending"},
        {"sku": "VND-BAD", "category": "food", "subcategory": "cake", "name": "Bad allergen", "unit": "flat", "unit_price": 1,
         "serves": 1, "allergens": ["gluten"], "status": "approved"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    items = load_vendor_items(path)
    assert [i.sku for i in items] == ["VND-SWEETCRUMBS-CAKE"]      # pending skipped, bad allergen skipped loudly
    assert items[0].price_basis == "quote" and "vendor" in items[0].tags
    merged = StaticCatalog.with_vendors(path)
    assert merged.get("VND-SWEETCRUMBS-CAKE") is not None and merged.get("FD-CAKE") is not None
    assert load_vendor_items(tmp_path / "missing.jsonl") == []


# ---------------------------------------------------------------- API
@pytest.fixture
def client():
    return TestClient(create_app())


def test_lookup_endpoint_contract(client):
    r = client.get("/api/v1/vendors/lookup", params={"sku": "ACT-MAGIC", "near": "Austin, TX"})
    assert r.status_code == 200
    d = r.json()
    assert d["query"] == "kids party magician" and d["links"] and d["sources_configured"] == []
    assert client.get("/api/v1/vendors/lookup", params={"sku": "NOPE", "near": "Austin"}).status_code == 404
    assert client.get("/api/v1/vendors/lookup", params={"sku": "ACT-MAGIC", "near": "A"}).status_code == 422
    assert client.get("/api/v1/vendors/lookup", params={"sku": "ACT-MAGIC", "near": "x" * 81}).status_code == 422
