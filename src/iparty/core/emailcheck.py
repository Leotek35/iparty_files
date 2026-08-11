"""Email typo detection: catch 'gamail.com' before it becomes a lost booking.

Design: only intervene when the typed domain is CLOSE to a popular consumer
domain (edit distance 1, or 2 for longer domains) or uses a known TLD typo.
Unknown-but-plausible business domains (leotek.tech) always pass — false
positives on legit domains are worse than missed typos.
"""
from __future__ import annotations

POPULAR_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "aol.com", "live.com", "msn.com", "protonmail.com", "proton.me",
    "googlemail.com", "yandex.com", "zoho.com", "gmx.com", "mail.com", "ymail.com",
]
_POPULAR = set(POPULAR_DOMAINS)

TLD_TYPOS = {"con": "com", "cmo": "com", "ocm": "com", "coom": "com",
             "comm": "com", "vom": "com", "cim": "com", "nte": "net", "ogr": "org"}


def _lev(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein distance with early-exit cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best_row = i
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            best_row = min(best_row, cur[j])
        if best_row > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def suggest_email(email: str) -> str | None:
    """Return a corrected email if the domain looks like a typo, else None."""
    if "@" not in email:
        return None
    local, _, domain = email.rpartition("@")
    domain = domain.lower()
    if domain in _POPULAR:
        return None

    # Known TLD typos work for ANY domain: leo@leotek.con -> leo@leotek.com
    name, _, tld = domain.rpartition(".")
    if name and tld in TLD_TYPOS:
        fixed = f"{name}.{TLD_TYPOS[tld]}"
        return f"{local}@{fixed}"

    best, best_dist = None, 3
    for d in POPULAR_DOMAINS:
        dist = _lev(domain, d, cap=2)
        if dist < best_dist:
            best, best_dist = d, dist
    if best is None:
        return None
    # distance 1: near-certain typo. distance 2: only for longer targets where
    # two edits still leave the intent unambiguous.
    if best_dist == 1 or (best_dist == 2 and len(best) >= 9):
        return f"{local}@{best}"
    return None
