"""Package the deep-testing suite into a distributable zip.

The four suite files live in tests/ as the single source of truth (they run in
CI like every other test); this script only packages them:

  tests/test_100_user_profiles_mece.py       100-profile MECE demand matrix
  tests/test_e2e_user_journeys.py            end-to-end journeys over the API
  tests/test_adversarial_security_fuzzing.py races, hostile input, email gate
  tests/test_mece_gap_partitions.py          feasibility/verifier/limiter gaps
  tests/test_living_pass_mece.py             Living Pass: 5 RSVP waves × every profile
  tests/test_living_pass_api.py              Living Pass: contract, credentials, fuzz
  tests/mece_profiles.py                     the shared 100-profile table

Usage:  python scripts/generate_test_suite_zip.py
Output: iparty_deep_testing_suite.zip (at the repo root)
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SUITE_FILES = [
    "tests/mece_profiles.py",
    "tests/test_100_user_profiles_mece.py",
    "tests/test_e2e_user_journeys.py",
    "tests/test_adversarial_security_fuzzing.py",
    "tests/test_mece_gap_partitions.py",
    "tests/test_living_pass_mece.py",
    "tests/test_living_pass_api.py",
]

ZIP_NAME = "iparty_deep_testing_suite.zip"


def create_and_pack_test_suite() -> Path:
    missing = [f for f in SUITE_FILES if not (REPO_ROOT / f).exists()]
    if missing:
        sys.exit(f"Suite files missing, nothing packaged: {missing}")

    zip_path = REPO_ROOT / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for rel in SUITE_FILES:
            zipf.write(REPO_ROOT / rel, arcname=rel)
            print(f" -> packed {rel}")
    print(f"\nSuccessfully packaged test suite into: {zip_path.name}")
    return zip_path


if __name__ == "__main__":
    create_and_pack_test_suite()
