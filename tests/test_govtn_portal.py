"""Tests for the official Tunisian government portal harvester.

This is the only authoritative source in the pipeline, and the only one that
covers the sitting government - which is exactly where the encyclopaedic
sources are thinnest.
"""
import pathlib

from govtn.sources.govtn_portal import parse_member

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load():
    html = (FIXTURES / "govtn_portal_member.html").read_text(encoding="utf-8")
    return parse_member(html, "https://www.tunisie.gov.tn/membre-de-gouvernement/155/x.htm")


def test_name_is_stripped_of_its_honorific():
    # Every name on the portal is prefixed السيد / السيدة.
    record = load()
    assert record["name"] == "ليلى  جفّال"
    assert not record["name"].startswith("السيد")


def test_ministry_and_function_are_separate_fields():
    record = load()
    assert record["function"] == "وزيرة العدل"
    assert record["ministry"] == "وزارة العدل"


def test_tatweel_padding_is_removed():
    # The portal pads titles for justification: وزارة العـــدل.
    assert "ـ" not in load()["ministry"]


def test_script_and_footer_names_are_ignored():
    record = load()
    assert record["name"] not in {"فلان الفلاني", "لا أحد"}


def test_official_arabic_title_maps_to_the_harmonised_portfolio():
    from govtn.normalize import parse_title
    record = load()
    parsed = parse_title(record["function"])
    assert parsed.portfolio == "justice"
    # The feminine form وزيرة must be recognised as the rank, like وزير.
    assert parsed.rank in {"minister", "minister_of_state"}
