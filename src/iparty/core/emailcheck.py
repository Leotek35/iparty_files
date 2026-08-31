"""Email acceptance + typo detection: catch 'gamail.com' (and throwaway
inboxes, and undeliverable shapes) before they become lost bookings.

Three layers, each with a distinct job:

1. `EMAIL_RE` / `validate_email_address` — SHAPE. Dot-atom local part (no
   leading/trailing/consecutive dots), alnum-with-inner-hyphen domain labels,
   alphabetic TLD. Deliberately stricter than full RFC 5322 (no quoted locals,
   no IP-literal domains): everything a real party parent types passes; the
   junk that breaks downstream mail delivery does not.
2. `DISPOSABLE_DOMAINS` — DURABILITY. A contact address that evaporates in ten
   minutes is a lost booking; known throwaway providers are rejected at
   capture time. Exact domain (or subdomain) match against a small curated
   list — never fuzzy, so legit business domains can't be caught by accident.
3. `suggest_email` — TYPOS. Only intervenes when the typed domain is CLOSE to
   a popular consumer domain (edit distance 1, or 2 for longer domains) or
   uses a known TLD typo. Unknown-but-plausible business domains
   (leotek.tech) always pass — false positives on legit domains are worse
   than missed typos.
"""
from __future__ import annotations

import re

EMAIL_MAX_LENGTH = 254   # RFC 5321 path limit
LOCAL_MAX_LENGTH = 64    # RFC 5321 local-part limit

EMAIL_RE = re.compile(
    r"^(?!\.)(?!.*\.\.)[A-Za-z0-9._%+\-]+(?<!\.)"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)

DISPOSABLE_DOMAINS = frozenset({
    "10minutemail.com", "dispostable.com", "disposablemail.com", "emailondeck.com",
    "fakeinbox.com", "getnada.com", "grr.la", "guerrillamail.com", "maildrop.cc",
    "mailinator.com", "mailnesia.com", "mintemail.com", "sharklasers.com",
    "spam4.me", "temp-mail.org", "tempinbox.com", "tempmail.com",
    "throwawaymail.com", "trashmail.com", "yopmail.com",
})


def is_disposable_domain(domain: str) -> bool:
    d = domain.lower().rstrip(".")
    return d in DISPOSABLE_DOMAINS or any(d.endswith("." + known) for known in DISPOSABLE_DOMAINS)


def email_invalid_reason(email: str) -> str | None:
    """Why `email` is unacceptable as a booking/vendor contact — or None if fine."""
    if len(email) > EMAIL_MAX_LENGTH:
        return "is too long to be a deliverable address"
    if not EMAIL_RE.match(email):
        return "is not a valid email address"
    local, _, domain = email.rpartition("@")
    if len(local) > LOCAL_MAX_LENGTH:
        return "is not a valid email address"
    if is_disposable_domain(domain):
        return "uses a disposable email domain; please use a lasting address"
    return None


def validate_email_address(email: str) -> bool:
    """True if `email` is deliverable-shaped and not a known throwaway domain."""
    return email_invalid_reason(email) is None


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
