"""Tests for Leaders.com.tn biographical extraction.

The fixtures mirror the phrasing of real Leaders profiles, including the two
decoys that broke earlier versions of the extractor: a birth date inside a
<script> tag and another in the page footer.
"""
import pathlib

from govtn.sources.leaders import parse_biography

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str):
    html = (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
    return parse_biography(html, f"https://www.leaders.com.tn/{name}")


def test_birth_extraction_prose_form():
    record = load("leaders_profile")
    assert record["birth_date"] == "1955-08-15"
    assert record["birth_date_precision"] == "day"
    assert record["birth_place"] == "Médenine"


def test_birth_extraction_label_form():
    # "Naissance : 31 juillet 1964 à Sbeitla" rather than "né le ...".
    record = load("leaders_directory")
    assert record["birth_date"] == "1964-07-31"
    assert record["birth_place"] == "Sbeitla"


def test_script_and_footer_dates_are_ignored():
    record = load("leaders_profile")
    assert record["birth_date"] != "1900-01-01"   # planted in a <script>
    assert record["birth_date"] != "1800-02-02"   # planted in the footer


def test_institution_keeps_its_full_name():
    # The French article must be consumed, not sliced into the name:
    # "du Lycée" must yield "Lycée de Médenine", never "ycée de Médenine".
    record = load("leaders_profile")
    institutions = record["education_institutions"]
    assert "École nationale de la marine marchande" in institutions
    assert "Lycée de Médenine" in institutions
    assert not any(i.startswith(("l'", "ycée", "cole")) for i in institutions)


def test_degree_and_institution_are_separate_variables():
    # "diplôme d'ingénieur" is a credential, not a school.
    profile = load("leaders_profile")
    assert profile["degrees"] == [{"degree": "diplôme d'ingénieur", "field": "génie maritime"}]
    assert "ingénieur en génie maritime" not in profile["education_institutions"]

    directory = load("leaders_directory")
    degree = directory["degrees"][0]
    assert degree["degree"] == "maîtrise"
    assert degree["field"] == "droit"
    assert degree["inst"] == "Faculté des sciences juridiques de Tunis"


def test_ambiguous_occupation_terms_do_not_overtrigger():
    # A merchant-marine "officier" is not a security professional; coding him
    # as one would corrupt the technocrat/security distinction.
    profile = load("leaders_profile")
    assert profile["profession_domains"] == ["engineering"]
    assert load("leaders_directory")["profession_domains"] == ["law"]


def test_every_extraction_carries_its_evidence():
    record = load("leaders_profile")
    assert record["source_url"].startswith("https://www.leaders.com.tn/")
    assert "birth" in record["evidence"] and "1955" in record["evidence"]["birth"]
