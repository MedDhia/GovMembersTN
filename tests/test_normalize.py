"""Tests for the normalisation layer.

These cases are drawn from real spelling variance in Tunisian sources; each
one is a merge that silently fails, or a false merge that silently happens,
if the corresponding fold is removed.
"""
import pytest

from govtn.normalize import (
    date_overlap_days,
    name_similarity,
    parse_date,
    parse_title,
    normalize_arabic,
    has_arabic,
)

MATCH_THRESHOLD = 0.6


@pytest.mark.parametrize("variants", [
    # French vs English romanisation, and the fused definite article.
    ("Béji Caïd Essebsi", "Beji Caid Essebsi", "El Béji Caïd Es-Sebsi"),
    # Doubled-consonant instability.
    ("Mohamed Ghannouchi", "Mohammed Ghannouchi", "Muhammad Ghannouchi"),
    # k/q and unstable final vowel.
    ("Kaïs Saïed", "Kais Saied", "Qais Sayed"),
    ("Zine El Abidine Ben Ali", "Zine el-Abidine Ben Ali", "Zin al-Abidin Bin Ali"),
    ("Ali Larayedh", "Ali Laarayedh", "Ali Laârayedh"),
    # Sun-letter assimilation written out in French.
    ("Abdelhamid Escheikh", "Abdel Hamid Cheikh"),
    # Middle name / maiden name present in one source only.
    ("Hédi Nouira", "Hédi Amara Nouira"),
    ("Najla Bouden", "Najla Bouden Romdhane"),
    ("Sara Zaafarani", "Sara Zaafarani Zenzri"),
])
def test_variants_of_one_person_match(variants):
    head = variants[0]
    for other in variants[1:]:
        assert name_similarity(head, other) >= MATCH_THRESHOLD, (head, other)


@pytest.mark.parametrize("a,b", [
    # Shared surname, different people - the classic false merge in this data.
    ("Mohamed Ghannouchi", "Rached Ghannouchi"),
    ("Hédi Nouira", "Hédi Baccouche"),
    ("Kamel Maddouri", "Kamel Morjane"),
    ("Ahmed Hachani", "Ahmed Ounaies"),
    ("Habib Essid", "Habib Bourguiba"),
    ("Ali Larayedh", "Ali Chaouch"),
])
def test_distinct_people_do_not_match(a, b):
    assert name_similarity(a, b) < MATCH_THRESHOLD, (a, b)


@pytest.mark.parametrize("raw,rank,portfolio", [
    ("Ministre de l'Intérieur", "minister", "interior"),
    ("وزير الداخلية", "minister", "interior"),
    ("Secrétaire d'État à l'Intérieur", "secretary_of_state", "interior"),
    ("Chef du gouvernement", "head_of_government", "head_of_government"),
    ("Ministre d'État", "minister_of_state", "without_portfolio"),
    ("Ministre des Affaires étrangères", "minister", "foreign_affairs"),
    ("وزير الشؤون الخارجية", "minister", "foreign_affairs"),
    # Higher education must win over the generic education pattern.
    ("Ministre de l'Enseignement supérieur et de la Recherche scientifique",
     "minister", "higher_education"),
    ("Ministre de l'Éducation nationale", "minister", "education"),
    # "économie numérique" must not be captured by the economy portfolio.
    ("Ministre des Technologies de la communication et de l'Économie numérique",
     "minister", "ict"),
    ("Ministre de l'Économie et du Plan", "minister", "economy_planning"),
    # The rank is delegate, but the policy domain is still defence.
    ("Ministre délégué auprès du Premier ministre chargé de la Défense nationale",
     "delegate_minister", "defence"),
])
def test_title_parsing(raw, rank, portfolio):
    parsed = parse_title(raw)
    assert parsed.rank == rank
    assert parsed.portfolio == portfolio


def test_interim_flagged():
    assert parse_title("Ministre de l'Intérieur par intérim").is_interim
    assert not parse_title("Ministre de l'Intérieur").is_interim


@pytest.mark.parametrize("raw,iso,precision", [
    ("6 novembre 1970", "1970-11-06", "day"),
    ("1970-11-02", "1970-11-02", "day"),
    ("1er mars 1980", "1980-03-01", "day"),
    ("November 6, 1970", "1970-11-06", "day"),
    ("14/01/2011", "2011-01-14", "day"),
    # Tunisian Arabic month names are French-derived, not Levantine.
    ("11 أكتوبر 2021", "2021-10-11", "day"),
    ("7 جانفي 2011", "2011-01-07", "day"),
    ("15 أفريل 1956", "1956-04-15", "day"),
    ("2 جوان 1970", "1970-06-02", "day"),
    ("1 جويلية 1988", "1988-07-01", "day"),
    # Arabic-Indic digits.
    ("٧ نوفمبر ١٩٨٧", "1987-11-07", "day"),
    # Reduced precision must be reported, not silently invented.
    ("novembre 1970", "1970-11-01", "month"),
    ("1970", "1970-01-01", "year"),
])
def test_date_parsing(raw, iso, precision):
    parsed = parse_date(raw)
    assert parsed.value is not None and parsed.value.isoformat() == iso
    assert parsed.precision == precision


def test_unparseable_date_is_not_invented():
    parsed = parse_date("date inconnue")
    assert parsed.value is None and parsed.precision == "unknown"


def test_arabic_folding():
    assert normalize_arabic("الداخليّة") == normalize_arabic("الداخليه")
    assert has_arabic("وزير") and not has_arabic("ministre")


def test_overlap_days():
    from datetime import date
    # Two tenures that overlap by exactly one year.
    assert date_overlap_days(
        date(2011, 1, 1), date(2013, 1, 1),
        date(2012, 1, 1), date(2014, 1, 1),
    ) == 366
    # Disjoint tenures never produce a co-membership tie.
    assert date_overlap_days(
        date(2011, 1, 1), date(2012, 1, 1),
        date(2013, 1, 1), date(2014, 1, 1),
    ) == 0
    # An open end is censored, not treated as infinite.
    assert date_overlap_days(
        date(2020, 1, 1), None,
        date(2019, 1, 1), date(2020, 7, 1),
        censor=date(2026, 1, 1),
    ) == 182
