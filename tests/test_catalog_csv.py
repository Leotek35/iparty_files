"""Vendor-onboarding safety: CSV catalog loading."""
import pytest

from iparty.pricing.catalog import load_catalog_csv


def test_template_loads_and_grounds():
    cat = load_catalog_csv("docs/gtm/vendor_catalog_template.csv")
    assert len(cat.all()) == 3
    assert cat.get("BAK-GF-CAKE").allergens == frozenset({"egg", "milk"})


def test_poisoned_allergen_data_fails_loudly(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("sku,category,name,unit,unit_price,serves,allergens\n"
                   "X1,food,Mystery,flat,10,10,peanutz\n")
    with pytest.raises(ValueError, match="unknown allergen"):
        load_catalog_csv(bad)


def test_empty_csv_rejected(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("sku,category,name,unit,unit_price,serves,allergens\n")
    with pytest.raises(ValueError, match="no items"):
        load_catalog_csv(empty)
