"""Tests for biography category parsing, French and Arabic.

Categories are a controlled vocabulary and far more reliable than prose, but
each edition has its own conventions and its own traps.
"""
import pytest

from govtn.sources.biographies import parse_categories


# --- French ---------------------------------------------------------------

def test_french_categories_yield_structured_fields():
    record = parse_categories([
        "Catégorie:Naissance en août 1955",
        "Catégorie:Naissance à Médenine",
        "Catégorie:Élève du Collège Sadiki",
        "Catégorie:Personnalité du Mouvement Ennahdha",
        "Catégorie:Prisonnier politique tunisien",
    ])
    assert record["birth"] == "1955-08-01"
    assert record["birth_precision"] == "month"
    assert record["birth_place"] == "Médenine"
    assert record["education_institutions"] == ["Collège Sadiki"]
    assert record["parties"] == ["Mouvement Ennahdha"]
    assert "political_prisoner" in record["flags"]


def test_french_feminine_forms_signal_gender():
    women = parse_categories(["Catégorie:Ingénieure tunisienne",
                              "Catégorie:Femme politique tunisienne"])
    assert women["gender_hint"] == "female"
    # The masculine is French's unmarked default and proves nothing.
    assert "gender_hint" not in parse_categories(["Catégorie:Ingénieur tunisien"])


def test_non_parties_are_kept_out_of_party_affiliation():
    record = parse_categories([
        "Catégorie:Personnalité du printemps arabe",
        "Catégorie:Membre de l'Académie tunisienne des sciences",
        "Catégorie:Personnalité du Néo-Destour",
    ])
    assert record["parties"] == ["Néo-Destour"]
    assert record["memberships"] == ["Académie tunisienne des sciences"]


# --- Arabic ---------------------------------------------------------------

def test_hijri_birth_year_is_not_mistaken_for_a_gregorian_one():
    """Arabic Wikipedia tags the birth year twice, Gregorian and Hijri.

    "مواليد 1374 هـ" alongside "مواليد 1955". Matching the year without
    excluding the Hijri marker puts the birth 580 years adrift, and the result
    looks entirely plausible in a table.
    """
    record = parse_categories(
        ["تصنيف:مواليد 1374 هـ", "تصنيف:مواليد 1955"], lang="ar"
    )
    assert record["birth"] == "1955-01-01"

    # Hijri alone must yield no birth year at all, rather than a wrong one.
    only_hijri = parse_categories(["تصنيف:مواليد 1374 هـ"], lang="ar")
    assert "birth" not in only_hijri


def test_arabic_categories_yield_structured_fields():
    record = parse_categories([
        "تصنيف:مواليد 1955",
        "تصنيف:مواليد في مدنين",
        "تصنيف:شخصيات حركة النهضة التونسية",
        "تصنيف:ضحايا التعذيب",
        "تصنيف:مهندسون تونسيون",
    ], lang="ar")
    assert record["birth_place"] == "مدنين"
    assert record["parties"] == ["حركة النهضة التونسية"]
    assert "political_prisoner" in record["flags"]
    assert "engineer" in record["flags"]


def test_arabic_values_are_not_returned_orthographically_folded():
    """Folding is for MATCHING only.

    Returning the folded string would store حركه النهضه instead of
    حركة النهضة, corrupting every Arabic value in the dataset.
    """
    record = parse_categories(["تصنيف:شخصيات حركة النهضة التونسية"], lang="ar")
    assert record["parties"] == ["حركة النهضة التونسية"]
    assert "حركه" not in record["parties"][0]


@pytest.mark.parametrize("category,expected", [
    ("تصنيف:أشخاص من ولاية مدنين", "مدنين"),   # governorate prefix dropped
    ("تصنيف:أشخاص من القيروان", "القيروان"),
])
def test_arabic_birthplace_forms(category, expected):
    assert parse_categories([category], lang="ar")["birth_place"] == expected


def test_arabic_feminine_plural_signals_gender():
    record = parse_categories(
        ["تصنيف:وزيرات تونسيات", "تصنيف:مهندسات تونسيات"], lang="ar"
    )
    assert record["gender_hint"] == "female"
    assert "gender_hint" not in parse_categories(
        ["تصنيف:وزراء تونسيون"], lang="ar"
    )


def test_arabic_education_is_captured():
    record = parse_categories(
        ["تصنيف:خريجو جامعة تونس"], lang="ar"
    )
    assert record["education_institutions"] == ["جامعة تونس"]
