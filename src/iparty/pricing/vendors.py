"""Real vendor listings — the catalog's bridge to the world outside it.

Three layers, all optional, none trusted blindly:

1. Live lookups (`VendorDirectory`): for a catalog SKU and a place ("Austin,
   TX"), the directory asks the configured sources — Google Places (New) Text
   Search, Yelp Fusion, Foursquare Places, or OpenStreetMap (Nominatim +
   Overpass) as a keyless fallback — for businesses that sell that kind of
   thing nearby. Results are *leads* (name, rating, distance, link), never
   prices: a price only enters a plan through the catalog.
2. Marketplace deep links (`marketplace_links`): search URLs on Thumbtack,
   GigSalad, The Bash, Peerspace and Yelp built from the item's vendor query,
   so a host can shop a line item in one click even with no API keys.
3. Vendor-onboarded rows (`load_vendor_items`): approved vendors' own items
   (data/vendor_catalog.jsonl) merged into the static catalog with
   `price_basis="quote"`, so a real quote can replace a research price.

Every source is cached, rate-tolerant and fails soft: an outage returns an
empty list and the plan is still verified against the catalog.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from ..core.config import settings
from ..core.logging import get_logger
from .catalog import CatalogItem, item_from_dict

logger = get_logger("vendors")

Fetch = Callable[[str, dict[str, str], dict[str, str] | None, dict[str, Any] | None], dict | None]


# ---------------------------------------------------------------------------
# What to search for
# ---------------------------------------------------------------------------
QUERY_BY_SUBCATEGORY: dict[str, str] = {
    "kids_venue": "kids party venue", "entertainment": "party venue", "hall": "event hall rental",
    "ballroom": "hotel ballroom event venue", "loft": "event space rental", "rooftop": "rooftop event venue",
    "garden": "garden event venue", "estate": "private estate wedding venue", "barn": "barn wedding venue",
    "yacht": "yacht charter", "studio": "event studio rental", "gallery": "art gallery event rental",
    "theater": "theater rental", "music": "live music venue", "taproom": "brewery taproom private events",
    "wellness": "spa private party", "restaurant": "restaurant private party room", "park": "park pavilion reservation",
    "event_space": "event space rental", "island": "private island charter", "outdoor": "farm party venue",
    "beach": "beach club events", "home": "party rental",
    "main": "catering", "side": "catering", "snack": "catering", "dessert": "dessert catering", "cake": "custom cakes bakery",
    "drink": "bar service catering",
    "tableware": "party supply store", "decor": "balloon decor party decorator", "lighting": "event lighting rental",
    "rentals": "party rental tables chairs tents", "favors": "party favors", "stationery": "invitation printing",
    "games": "party games rental", "inflatables": "bounce house rental", "workshop": "party workshop class",
    "photo": "event photographer", "staffing": "event staffing", "planning": "event planner", "transport": "limo service",
    "tech": "gaming party rental", "effects": "special effects event", "ceremony": "officiant", "sports": "sports party coach",
}
QUERY_BY_SKU_PREFIX: dict[str, str] = {
    "ACT-DJ": "party DJ", "ACT-LIVE-BAND": "live band for events", "ACT-MAGIC": "kids party magician",
    "ACT-FACE": "face painter", "ACT-BOUNCE": "bounce house rental", "ACT-PHOTO-BOOTH": "photo booth rental",
    "ACT-PHOTOGRAPHER": "event photographer", "ACT-MARIACHI": "mariachi band", "ACT-STRING": "string quartet",
    "ACT-JAZZ": "jazz trio", "ACT-KARAOKE": "karaoke rental", "ACT-LASER": "mobile laser tag", "ACT-PETTING": "mobile petting zoo",
    "ACT-PONY": "pony rides party", "ACT-HENNA": "henna artist", "ACT-CASINO": "casino party rental",
    "ACT-COCKTAIL": "mixology class", "ACT-WINE": "sommelier wine tasting", "ACT-POTTERY": "pottery class party",
    "ACT-PAINT": "paint and sip", "ACT-SPA": "mobile spa party", "ACT-VR": "VR party rental", "ACT-LAN": "LAN party rental",
    "ACT-FIREWORKS": "fireworks display company", "ACT-KOSHER": "kosher caterer supervision",
    "FD-PIZZA": "pizza catering", "FD-TACO": "taco catering", "FD-BBQ": "bbq catering", "FD-SUSHI": "sushi catering",
    "FD-KOSHER": "kosher caterer", "FD-HALAL": "halal caterer", "FD-SHAWARMA": "halal catering", "FD-BIRYANI": "indian catering halal",
    "FD-INDIAN": "indian catering", "FD-CHINESE": "chinese banquet catering", "FD-DIM": "dim sum catering",
    "FD-CAKE": "custom cake bakery", "FD-ICE-CREAM-TRUCK": "ice cream truck party", "FD-FOOD-TRUCK": "food truck catering",
    "FD-OPEN-BAR": "bartending service", "FD-BEER": "bartending service", "FD-ESPRESSO": "espresso cart catering",
    "SUP-FLORAL": "event florist", "SUP-BALLOON": "balloon decorator", "SUP-TENT": "tent rental", "SUP-CHINA": "event rentals china glassware",
    "SUP-LIGHTING": "event lighting", "SUP-INVITES": "invitation printing", "SUP-NEON": "custom neon sign",
    "VEN-REST": "restaurant private dining", "VEN-KIDS": "kids party venue", "VEN-TRAMPOLINE": "trampoline park",
    "VEN-BOWLING": "bowling alley party", "VEN-ARCADE": "arcade party", "VEN-ESCAPE": "escape room", "VEN-POOL": "pool rental party",
}


def vendor_query(item: CatalogItem) -> str:
    """The search phrase a host would type for this line item."""
    for prefix, query in sorted(QUERY_BY_SKU_PREFIX.items(), key=lambda kv: -len(kv[0])):
        if item.sku.startswith(prefix):
            return query
    cuisine = next((t[8:].replace("_", " ") for t in sorted(item.tags) if t.startswith("cuisine:")), "")
    base = QUERY_BY_SUBCATEGORY.get(item.subcategory, item.category)
    if item.category == "food" and cuisine and cuisine not in ("american", "bbq"):
        base = f"{cuisine} {base}"
    if "halal" in item.certifications:
        base = f"halal {base}"
    if "kosher" in item.certifications:
        base = f"kosher {base}"
    return base


def marketplace_links(item: CatalogItem, near: str = "") -> list[dict[str, str]]:
    """One-click shopping links for a line item — no API keys needed."""
    q = quote_plus(vendor_query(item))
    loc = quote_plus(near) if near else ""
    links = [
        {"source": "Yelp", "url": f"https://www.yelp.com/search?find_desc={q}" + (f"&find_loc={loc}" if loc else "")},
        {"source": "Thumbtack", "url": f"https://www.thumbtack.com/search/?query={q}" + (f"&zip_code={loc}" if loc else "")},
    ]
    if item.category == "activities":
        links.append({"source": "GigSalad", "url": f"https://www.gigsalad.com/search?q={q}" + (f"&location={loc}" if loc else "")})
        links.append({"source": "The Bash", "url": f"https://www.thebash.com/search?q={q}"})
    if item.category == "venue":
        links.append({"source": "Peerspace", "url": f"https://www.peerspace.com/s?q={q}" + (f"&location={loc}" if loc else "")})
    return links


# ---------------------------------------------------------------------------
# Listings and sources
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VendorListing:
    source: str
    name: str
    address: str = ""
    rating: float | None = None
    reviews: int | None = None
    price_level: str | None = None
    url: str = ""
    external_id: str = ""     # place_id / business id — cacheable; never PII
    distance_m: int | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, "")}


def _default_fetch(url: str, params: dict[str, str], headers: dict[str, str] | None = None,
                   json_body: dict[str, Any] | None = None) -> dict | None:
    """Tiny HTTP shim (httpx, imported lazily so tests never need the network)."""
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx is a dev/optional dependency
        logger.warning("httpx not installed; vendor lookups disabled")
        return None
    try:
        with httpx.Client(timeout=6.0) as client:
            if json_body is not None:
                resp = client.post(url, params=params, headers=headers or {}, json=json_body)
            else:
                resp = client.get(url, params=params, headers=headers or {})
            if resp.status_code != 200:
                logger.warning("vendor source %s returned %s", url.split("?")[0], resp.status_code)
                return None
            return resp.json()
    except Exception as exc:  # noqa: BLE001 - any outage is a soft failure
        logger.warning("vendor source %s failed: %s", url.split("?")[0], exc.__class__.__name__)
        return None


class _Cache:
    def __init__(self, ttl: float) -> None:
        self.ttl = ttl
        self._data: dict[tuple, tuple[float, list[VendorListing]]] = {}

    def get(self, key: tuple) -> list[VendorListing] | None:
        hit = self._data.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        return None

    def put(self, key: tuple, value: list[VendorListing]) -> None:
        self._data[key] = (time.monotonic(), value)
        if len(self._data) > 2000:
            oldest = sorted(self._data.items(), key=lambda kv: kv[1][0])[:500]
            for k, _ in oldest:
                self._data.pop(k, None)


class GooglePlacesSource:
    """Google Places API (New) Text Search. Pro field mask only: identifiers,
    name, address, rating, price level, maps link. Results are cached briefly
    (place_id may be stored indefinitely per policy; everything else is transient)."""

    name = "google_places"
    ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
    FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.priceLevel,places.googleMapsUri"
    TTL = 300.0

    def __init__(self, api_key: str, fetch: Fetch = _default_fetch) -> None:
        self.api_key, self.fetch, self.cache = api_key, fetch, _Cache(self.TTL)

    def search(self, query: str, near: str, limit: int = 5) -> list[VendorListing]:
        key = (query, near.lower(), limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        body = {"textQuery": f"{query} near {near}", "maxResultCount": max(1, min(limit, 10))}
        headers = {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": self.FIELD_MASK, "Content-Type": "application/json"}
        data = self.fetch(self.ENDPOINT, {}, headers, body) or {}
        out = []
        for p in data.get("places", [])[:limit]:
            out.append(VendorListing(
                source=self.name, name=(p.get("displayName") or {}).get("text", ""), address=p.get("formattedAddress", ""),
                rating=p.get("rating"), reviews=p.get("userRatingCount"), price_level=p.get("priceLevel"),
                url=p.get("googleMapsUri", ""), external_id=p.get("id", ""),
            ))
        self.cache.put(key, out)
        return out


class YelpSource:
    """Yelp Fusion business search (24h cache per Yelp's terms)."""

    name = "yelp"
    ENDPOINT = "https://api.yelp.com/v3/businesses/search"
    TTL = 24 * 3600.0

    def __init__(self, api_key: str, fetch: Fetch = _default_fetch) -> None:
        self.api_key, self.fetch, self.cache = api_key, fetch, _Cache(self.TTL)

    def search(self, query: str, near: str, limit: int = 5) -> list[VendorListing]:
        key = (query, near.lower(), limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        params = {"term": query, "location": near, "limit": str(max(1, min(limit, 20))), "sort_by": "best_match"}
        data = self.fetch(self.ENDPOINT, params, {"Authorization": f"Bearer {self.api_key}"}, None) or {}
        out = []
        for b in data.get("businesses", [])[:limit]:
            loc = b.get("location") or {}
            out.append(VendorListing(
                source=self.name, name=b.get("name", ""), address=", ".join(loc.get("display_address") or []),
                rating=b.get("rating"), reviews=b.get("review_count"), price_level=b.get("price"),
                url=b.get("url", ""), external_id=b.get("id", ""),
                distance_m=int(b["distance"]) if isinstance(b.get("distance"), (int, float)) else None,
            ))
        self.cache.put(key, out)
        return out


class FoursquareSource:
    """Foursquare Places search."""

    name = "foursquare"
    ENDPOINT = "https://api.foursquare.com/v3/places/search"
    TTL = 24 * 3600.0

    def __init__(self, api_key: str, fetch: Fetch = _default_fetch) -> None:
        self.api_key, self.fetch, self.cache = api_key, fetch, _Cache(self.TTL)

    def search(self, query: str, near: str, limit: int = 5) -> list[VendorListing]:
        key = (query, near.lower(), limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        params = {"query": query, "near": near, "limit": str(max(1, min(limit, 20)))}
        data = self.fetch(self.ENDPOINT, params, {"Authorization": self.api_key, "Accept": "application/json"}, None) or {}
        out = []
        for r in data.get("results", [])[:limit]:
            loc = r.get("location") or {}
            out.append(VendorListing(
                source=self.name, name=r.get("name", ""), address=loc.get("formatted_address", ""),
                rating=r.get("rating"), url=r.get("website", "") or f"https://foursquare.com/v/{r.get('fsq_id', '')}",
                external_id=r.get("fsq_id", ""), distance_m=r.get("distance"),
            ))
        self.cache.put(key, out)
        return out


_OSM_TAGS: dict[str, str] = {
    "catering": '["craft"="caterer"]', "bakery": '["shop"="bakery"]', "restaurant": '["amenity"="restaurant"]',
    "venue": '["amenity"~"events_venue|community_centre"]', "party supply": '["shop"~"party|gift"]',
    "photographer": '["craft"="photographer"]', "florist": '["shop"="florist"]', "brewery": '["craft"="brewery"]',
    "escape room": '["leisure"="escape_game"]', "bowling": '["leisure"="bowling_alley"]', "arcade": '["leisure"="amusement_arcade"]',
    "trampoline": '["leisure"="trampoline_park"]', "spa": '["leisure"="spa"]', "park": '["leisure"="park"]',
}


class OverpassSource:
    """Keyless fallback: Nominatim geocodes the place, Overpass lists tagged
    businesses within a few kilometres. Only used when enabled — public OSM
    endpoints ask for gentle use, so results are cached a day."""

    name = "openstreetmap"
    NOMINATIM = "https://nominatim.openstreetmap.org/search"
    OVERPASS = "https://overpass-api.de/api/interpreter"
    TTL = 24 * 3600.0

    def __init__(self, fetch: Fetch = _default_fetch) -> None:
        self.fetch, self.cache = fetch, _Cache(self.TTL)

    def _tag(self, query: str) -> str:
        q = query.lower()
        for word, tag in _OSM_TAGS.items():
            if word in q:
                return tag
        return '["shop"]'

    def search(self, query: str, near: str, limit: int = 5) -> list[VendorListing]:
        key = (query, near.lower(), limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        headers = {"User-Agent": "iParty/1.0 (vendor lookup)"}
        geo = self.fetch(self.NOMINATIM, {"q": near, "format": "json", "limit": "1"}, headers, None)
        if not geo or not isinstance(geo, list):
            return []
        lat, lon = geo[0].get("lat"), geo[0].get("lon")
        if lat is None or lon is None:
            return []
        ql = f'[out:json][timeout:8];nwr{self._tag(query)}(around:6000,{lat},{lon});out center {max(1, min(limit, 20))};'
        data = self.fetch(self.OVERPASS, {"data": ql}, headers, None) or {}
        out = []
        for el in data.get("elements", [])[:limit]:
            tags = el.get("tags") or {}
            if not tags.get("name"):
                continue
            addr = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")) if x)
            out.append(VendorListing(source=self.name, name=tags["name"], address=addr, url=tags.get("website", ""),
                                     external_id=f"{el.get('type')}/{el.get('id')}"))
        self.cache.put(key, out)
        return out


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------
@dataclass
class VendorDirectory:
    sources: list[Any] = field(default_factory=list)

    @classmethod
    def from_settings(cls, fetch: Fetch = _default_fetch) -> VendorDirectory:
        sources: list[Any] = []
        if settings.GOOGLE_PLACES_API_KEY:
            sources.append(GooglePlacesSource(settings.GOOGLE_PLACES_API_KEY, fetch))
        if settings.YELP_API_KEY:
            sources.append(YelpSource(settings.YELP_API_KEY, fetch))
        if settings.FOURSQUARE_API_KEY:
            sources.append(FoursquareSource(settings.FOURSQUARE_API_KEY, fetch))
        if settings.OSM_FALLBACK_ENABLED:
            sources.append(OverpassSource(fetch))
        return cls(sources)

    def configured(self) -> list[str]:
        return [s.name for s in self.sources]

    def lookup(self, item: CatalogItem, near: str, limit: int = 5) -> dict:
        """Leads for a line item near a place. Sources are tried in order; the
        first that answers wins, outages fall through, and the marketplace
        links are always there."""
        query = vendor_query(item)
        listings: list[VendorListing] = []
        source_used = None
        for source in self.sources:
            try:
                found = source.search(query, near, limit)
            except Exception as exc:  # noqa: BLE001 - never let a vendor outage break planning
                logger.warning("vendor source %s raised %s", source.name, exc.__class__.__name__)
                found = []
            if found:
                listings, source_used = found, source.name
                break
        return {
            "sku": item.sku, "name": item.name, "query": query, "near": near,
            "source": source_used, "listings": [v.as_dict() for v in listings],
            "links": marketplace_links(item, near),
            "note": "Listings are leads, not quotes — the plan is priced from the catalog until a vendor quote is approved.",
        }


# ---------------------------------------------------------------------------
# Vendor-onboarded catalog rows
# ---------------------------------------------------------------------------
def load_vendor_items(path: str | Path | None = None) -> list[CatalogItem]:
    """Approved vendor rows (JSONL, one catalog item per line, `status: approved`)
    become real catalog items priced by quote. Rows that fail validation are
    skipped with a warning — a vendor typo must never break planning."""
    p = Path(path or settings.VENDOR_CATALOG_PATH)
    if not p.exists():
        return []
    items: list[CatalogItem] = []
    with p.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("status", "approved") != "approved":
                    continue
                row.setdefault("price_basis", "quote")
                row["tags"] = sorted({*(row.get("tags") or []), "vendor", *([] if any(str(t).startswith("seg:") for t in (row.get("tags") or [])) else ["seg:all"])})
                items.append(item_from_dict(row))
            except Exception as exc:  # noqa: BLE001
                logger.warning("vendor catalog %s line %d skipped: %s", p, n, exc)
    return items


def gather_lookups(directory: VendorDirectory, items: list[CatalogItem], near: str, limit: int = 3) -> list[dict]:
    return [directory.lookup(item, near, limit) for item in items]
