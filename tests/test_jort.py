"""Tests for the Journal Officiel harvester.

The gazette is the authoritative record of a ministerial appointment, so a
wrong citation is worse than none: it lends official weight to a claim the
gazette does not make.
"""
import pytest

from govtn.sources.jort import (
    JortClient,
    _ISSUE_DATE,
    _NOT_CABINET,
    extract_holder,
)
from govtn.normalize import parse_date


RESULT_HTML = """
<ul>
<li class="p-4 rounded-lg">
  <div class="flex"><span>Journal Officiel</span> · <span>2023 / N°085</span>
  · <span>page 3</span> · <span class="uppercase">fr</span></div>
  <div class="text-sm">...Article premier - Monsieur Ahmed Hachani est
  nomm&eacute; Chef du Gouvern...</div>
  <a href="/sign-in">🔒 Se connecter pour voir</a>
</li>
<li class="p-4 rounded-lg">
  <div class="flex"><span>Annonces L&eacute;gales</span> · <span>2025 / N°068</span>
  · <span>page 86</span> · <span class="uppercase">fr</span></div>
  <div class="text-sm">...CHARFEDDINE SONIA MOH...</div>
</li>
</ul>
"""


def test_result_metadata_is_parsed():
    hits = JortClient._parse_results(RESULT_HTML)
    assert len(hits) == 2
    first = hits[0]
    assert first.collection == "Journal Officiel"
    assert (first.year, first.issue, first.page, first.lang) == (2023, "085", 3, "fr")
    assert first.is_nomination


def test_citation_is_human_lookupable():
    hit = JortClient._parse_results(RESULT_HTML)[0]
    assert hit.as_citation() == "JORT 2023, N°085, p. 3 (fr)"


@pytest.mark.parametrize("snippet,expected", [
    ("...Article premier - Monsieur Ahmed Hachani est nommé Chef du Gouvern...",
     "Ahmed Hachani"),
    ("...Monsieur Habib Essid est nommé chef du gouvernem...", "Habib Essid"),
    # A rank between the name and the verb must not be swallowed into the name.
    ("...Monsieur Hédi Majdoub , conseiller des services publics, est nommé ...",
     "Hédi Majdoub"),
])
def test_holder_extraction(snippet, expected):
    assert extract_holder(snippet) == expected


def test_collective_decrees_yield_no_single_holder():
    # "Sont nommés membres du Gouvernement Mesdames et Messieurs ..." names
    # many people; inventing one from it would be wrong.
    assert extract_holder(
        "...Article premier - Sont nommés membres du Gouvernement Mesdames et ..."
    ) is None


def test_diplomatic_rank_is_not_a_cabinet_post():
    """"Ministre plénipotentiaire" is a diplomatic rank, not a seat in cabinet.

    It dominates the "est nommé ministre" results and would otherwise fill the
    dataset with false ministerial appointments.
    """
    assert _NOT_CABINET.search("Monsieur X est nommé Ministre Plénipotentiaire")
    assert not _NOT_CABINET.search("Monsieur X est nommé ministre de l'intérieur")


def test_issue_date_takes_the_gregorian_half_not_the_hijri():
    """Issues are dated in both calendars: "26 chaâbane 1442 – 8 avril 2021".

    Taking the first number in the line yields 1442.
    """
    line = "Jeudi 26 chaâbane 1442 – 8 avril 2021 164ème année N° 32"
    match = _ISSUE_DATE.search(line)
    assert match
    parsed = parse_date(match.group(1))
    assert parsed.value is not None and parsed.value.isoformat() == "2021-04-08"


def test_undeclared_charset_is_sniffed_not_assumed_latin1(tmp_path, monkeypatch):
    """requests defaults to ISO-8859-1 when a response declares no charset.

    jort.tn declares none, so its UTF-8 came back as "NÂ°032" and "nommÃ©",
    and every regex against it failed in ways that looked like a parser bug.

    `Fetcher` writes a cache directory and a manifest as a side effect of
    construction, under `config.paths().raw`. Left pointing at the real tree
    this drops a `data/raw/charset-test/` into the working copy on every run -
    harmless while `.gitignore` swallowed every manifest, and a file waiting to
    be committed by accident now that the manifests are tracked. `GOVTN_ROOT`
    is the override the config module documents for exactly this.
    """
    import requests
    from govtn.http import Fetcher

    class FakeResponse:
        status_code = 200
        headers: dict = {}
        url = "https://jort.tn/"
        encoding = "ISO-8859-1"          # what requests assumes with no charset
        apparent_encoding = "utf-8"
        content = "Journal Officiel · N°032 nommé".encode("utf-8")

        @property
        def text(self):
            return self.content.decode(self.encoding)

        def raise_for_status(self):
            return None

    monkeypatch.setenv("GOVTN_ROOT", str(tmp_path))
    fetcher = Fetcher(source="charset-test", rate_limit=0)
    assert fetcher.manifest_path.is_relative_to(tmp_path), (
        "the fetcher is still writing into the real data/raw/")
    fetcher.session.get = lambda *a, **k: FakeResponse()
    text = fetcher.get("https://jort.tn/probe")
    assert "N°032" in text and "nommé" in text
    assert "Â°" not in text and "Ã©" not in text


# --- extraction robustness -------------------------------------------------

@pytest.mark.parametrize("snippet,expected", [
    # Snippets are cut to a fixed width and often begin mid-word. Requiring
    # the whole of "Monsieur" discarded a large share of perfect matches.
    ("...sieur Mohamed MZALI est nommé Premier Ministre à compter du 23 avr...",
     "Mohamed MZALI"),
    ("...dame Najla Bouden est nommée cheffe du gouvernement...", "Najla Bouden"),
    # Tunisian names carry particles; a four-token cap rejected exactly the
    # multi-particle names that matter most. (OCR reads "Zine" as "Zinc".)
    ("...Monsieur Zinc El Abidine Ben Ali est nommé Premier ministre , minis...",
     "Zinc El Abidine Ben Ali"),
])
def test_truncated_honorifics_and_long_names(snippet, expected):
    assert extract_holder(snippet) == expected


def test_preamble_references_are_not_decrees():
    """A decree's preamble cites the decrees it relies on.

    "وعلى الأمر عدد ... المتعلق بتسمية أعضاء الحكومة" is "having regard to
    decree no. X concerning the naming of members of the government" - a
    reference TO an appointment decree, not one. These were the single largest
    group of unparseable results.
    """
    from govtn.sources.jort import _PREAMBLE_REFERENCE
    assert _PREAMBLE_REFERENCE.search(
        "...وعلى الأمر عدد 51 لسنة 2021 المتعلق ب تسمية أعضاء الحكومة..."
    )
    assert not _PREAMBLE_REFERENCE.search(
        "...Article premier - Monsieur Ahmed Hachani est nommé Chef du Gouvern..."
    )


@pytest.mark.parametrize("snippet,portfolio", [
    ("...Monsieur X est nommé ministre de l'intérieur , et...", "interior"),
    ("...Article premier - Monsieur Ahmed Hachani est nommé Chef du Gouvern...",
     "head_of_government"),
    ("...dame Najla Bouden est nommée cheffe du gouvernement...",
     "head_of_government"),
])
def test_office_is_extracted_and_maps_to_a_portfolio(snippet, portfolio):
    """The office named in a decree disambiguates which appointment it records.

    Date proximity alone picks arbitrarily between the several posts a person
    may hold within a year.
    """
    from govtn.sources.jort import extract_office
    from govtn.normalize import parse_title
    office = extract_office(snippet)
    assert office
    assert parse_title(office).portfolio == portfolio
