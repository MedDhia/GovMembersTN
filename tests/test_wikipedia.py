"""Tests for the Wikipedia cabinet-roster parser.

The fixtures reproduce the three layouts that actually occur in French
Wikipedia's Tunisian cabinet articles: a clean wikitable with one cell per
line, a bullet list (the usual layout for the 1950s-60s governments), and a
table with inline cells, section separator rows, flag templates and footnotes.
"""
import pathlib

import pytest

from govtn.sources.wikipedia import (
    parse_cabinet_article,
    parse_infobox_dates,
    parse_lists,
    parse_tables,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / f"{name}.wiki").read_text(encoding="utf-8")


def test_table_layout_extracts_every_row():
    rows = parse_tables(load("cabinet_table"))
    assert len(rows) == 6
    by_title = {r["raw_title"]: r for r in rows}
    assert by_title["Ministre de l'Intérieur"]["person_name"] == "Taoufik Charfeddine"
    # The wikilink target is the join key to Wikidata and must survive.
    assert by_title["Ministre de la Justice"]["person_wikilink"] == "Leïla Jaffel"
    # A piped party link must yield the display text, not the target.
    assert by_title["Cheffe du gouvernement"]["party"] == "Indépendant"


def test_list_layout_extracts_every_row():
    rows = parse_lists(load("cabinet_list"))
    assert len(rows) == 5
    titles = {r["raw_title"] for r in rows}
    assert "Premier ministre" in titles
    assert "Secrétaire d'État à la Présidence du Conseil" in titles
    # Prose bullets that are not offices must not be picked up.
    assert not any("Liste des chefs" in r["raw_title"] for r in rows)


def test_messy_table_inline_cells_and_separators():
    rows = parse_tables(load("cabinet_messy"))
    # Five officeholders; the two "colspan" section headers are not people.
    assert len(rows) == 5
    assert not any("Secrétaires d'État" == r["raw_title"] for r in rows)
    by_title = {r["raw_title"]: r for r in rows}
    # A flag template in the cell must not leak into the name.
    assert by_title["Premier ministre"]["person_name"] == "Hédi Nouira"
    # A <ref> footnote must be removed whole, not just its tags.
    assert by_title["Secrétaire d'État aux Affaires culturelles"]["person_name"] == "Chedli Klibi"
    assert by_title["Ministre de l'Intérieur"]["date_note"] == "6 novembre 1970"


@pytest.mark.parametrize("fixture,start,end", [
    ("cabinet_table", "2021-10-11", "2023-08-01"),
    ("cabinet_list", "1956-04-15", "1957-07-25"),
    ("cabinet_messy", "1970-11-02", "1980-04-23"),
])
def test_infobox_dates(fixture, start, end):
    info = parse_infobox_dates(load(fixture))
    assert info["start_date"] == start
    assert info["end_date"] == end
    assert info["start_precision"] == "day"


def test_tables_win_over_lists_when_both_present():
    # The table fixture has no bullet roster; the list fixture has no table.
    # Where an article carries both, the bullet list is normally a prose
    # restatement of the table and must not double-count.
    table = parse_cabinet_article("t", load("cabinet_table"))
    assert table["n_table_rows"] == 6
    assert len(table["members"]) == table["n_table_rows"]

    combined = load("cabinet_table") + "\n\n== Résumé ==\n" + \
        "\n".join(f"* {r['raw_title']} : [[{r['person_name']}]]" for r in table["members"])
    record = parse_cabinet_article("t", combined)
    assert record["n_list_rows"] > 0
    assert len(record["members"]) == 6, "list rows must not be appended to table rows"


def test_members_are_deduplicated():
    doubled = load("cabinet_table") + "\n" + load("cabinet_table")
    record = parse_cabinet_article("t", doubled)
    assert len(record["members"]) == 6


def test_table_caption_is_not_parsed_as_a_header_cell():
    """Regression: a `|+` caption became phantom column 0 of the header row.

    That shifted every column index by one against the data rows, so the
    portfolio and person columns pointed at the wrong cells and the rows were
    dropped for being too short. Whole cabinets parsed to zero members -
    "Gouvernement Hamed Karoui" yielded 0 instead of 153.
    """
    rows = parse_tables(load("cabinet_caption"))
    assert len(rows) == 3, "caption row must not shift the column mapping"
    by_title = {r["raw_title"]: r for r in rows}
    assert by_title["Premier ministre"]["person_name"] == "Hamed Karoui"
    assert by_title["Ministre de l'Intérieur"]["person_name"] == "Chédli Neffati"
    # The party column must land on the party, not on the colour-swatch cell.
    assert by_title["Ministre de la Justice"]["party"] == "RCD"
    # And the caption itself must never surface as an officeholder.
    assert not any("Composition" in r["raw_title"] for r in rows)


def test_bold_and_image_cells_do_not_corrupt_values():
    rows = {r["raw_title"]: r for r in parse_tables(load("cabinet_caption"))}
    # Bold markup around a piped wikilink must yield the display text.
    assert rows["Premier ministre"]["person_wikilink"] == "Hamed Karoui"
    # An image cell must not be mistaken for the portfolio.
    assert not any(r["raw_title"].startswith("Fichier") for r in rows.values())


def test_image_size_is_not_read_as_a_portfolio():
    """Regression: `[[Fichier:x.jpg|60px]]` strips to "60px".

    When an image column was picked as the portfolio column, every row in the
    cabinet became a minister of "60px".
    """
    wikitext = """{| class="wikitable"
|-
| [[Fichier:Sin foto.svg|60px]]
| Ministre de l'Intérieur
| [[Taïeb Mehiri]]
|}"""
    rows = parse_tables(wikitext)
    assert not any(r["raw_title"].strip() == "60px" for r in rows)
    assert not any(r["person_name"].strip() == "60px" for r in rows)


def test_table_caption_supplies_a_composition_date():
    """Each roster table is captioned with its own composition/reshuffle date.

    Using it turns a cabinet-inherited span into a real individual start date.
    The caption's value sits inside a {{date|...}} template, so it must be
    UNWRAPPED, not stripped: `_cell_text` removes templates and left
    "Composition le" with no date at all, losing every captioned table.
    """
    wikitext = """{| class="wikitable"
|+ Composition le {{date|27 septembre 1989}}
! Portefeuille !! Nom
|-
| Ministre de l'Intérieur || [[Chédli Neffati]]
|}"""
    rows = parse_tables(wikitext)
    assert len(rows) == 1
    assert rows[0]["table_date"] == "1989-09-27"
    assert rows[0]["table_date_precision"] == "day"


def test_reshuffle_tables_get_their_own_dates():
    wikitext = """{| class="wikitable"
|+ Composition le {{date|27 septembre 1989}}
! Portefeuille !! Nom
|-
| Ministre de l'Intérieur || [[A]]
|}
{| class="wikitable"
|+ Postes remaniés le {{date|3 mars 1990}}
! Portefeuille !! Nom
|-
| Ministre de l'Intérieur || [[B]]
|}"""
    dates = {r["person_name"]: r["table_date"] for r in parse_tables(wikitext)}
    assert dates == {"A": "1989-09-27", "B": "1990-03-03"}


def test_caption_without_a_date_yields_none():
    wikitext = """{| class="wikitable"
|+ Membres du gouvernement
! Portefeuille !! Nom
|-
| Ministre de la Justice || [[C]]
|}"""
    assert parse_tables(wikitext)[0]["table_date"] is None


def test_each_edition_declares_its_own_index():
    """Reusing the French category name for Arabic returned zero articles.

    Arabic cabinets were then only reachable through French langlinks, which
    silently missed every government having an Arabic article and no French
    one - including the three most recent (Hachani, Madouri, Zaafarani), whose
    ministers were absent from the dataset entirely.
    """
    from govtn import config
    editions = {e["lang"]: e for e in config.sources()["wikipedia"]["editions"]}
    assert editions["ar"]["index_category"] == "تصنيف:مجالس وزراء تونس"
    assert editions["ar"]["index_category"] != editions["fr"]["index_category"]
    # French keeps its navigation template; Arabic has no equivalent.
    assert "index_template" in editions["fr"]


def test_non_french_discovery_unions_langlinks_with_the_local_index():
    import inspect
    from govtn.sources import wikipedia
    body = inspect.getsource(wikipedia.harvest)
    # The local index must be consulted unconditionally, not only when
    # langlinks come back empty.
    assert "own = discover_cabinet_articles" in body
    assert "if not mapping" not in body, "local index must not be a mere fallback"


# --- colspan alignment ------------------------------------------------------

MECHICHI_TABLE = """{| class="wikitable"
|+Composition au 11 octobre 2021
|-
! Poste
! colspan=2 | Titulaire
! Parti
|-
| '''[[Chef du gouvernement tunisien|Chef du gouvernement]]'''
| {{Infobox Parti politique tunisien/couleurs|Autre}} |
| ''Poste vacant''
|
|-
| [[Ministère de l'Intérieur (Tunisie)|Ministre de l'Intérieur]] <small>(intérim)</small>
| {{Infobox Parti politique tunisien/couleurs|Autre}} |
| [[Ridha Gharsallaoui]]
| [[Indépendant (politique)|Indépendant]]
|-
| [[Ministère du Commerce (Tunisie)|Ministre du Commerce]]<br>[[Ministère de l'Industrie (Tunisie)|Ministre de l'Industrie]] <small>(intérim)</small>
| {{Infobox Parti politique tunisien/couleurs|Autre}} |
| [[Mohamed Bousaïd]]
| Indépendant
|}"""


def test_colspan_header_does_not_shift_the_person_column():
    """The FR cabinet tables put a colour swatch and the name under one header.

    `! colspan=2 | Titulaire` covers two columns. Emitting one header cell made
    the header shorter than its rows, so every index shifted left and the
    person column landed on the swatch - which strips to a bare "|". Sixteen
    ministers of the Mechichi cabinet were harvested with the literal name "|",
    in the least-documented period of the dataset.
    """
    rows = parse_tables(MECHICHI_TABLE)
    names = [r["person_name"] for r in rows]
    assert "Ridha Gharsallaoui" in names
    assert "Mohamed Bousaïd" in names
    assert not any(set(name) <= set("| \t") for name in names), names


def test_vacant_posts_are_not_people():
    """"Poste vacant" is a statement that nobody holds the office."""
    rows = parse_tables(MECHICHI_TABLE)
    names = [r["person_name"].lower() for r in rows]
    assert not any("vacant" in name for name in names), names
    # And its Arabic equivalent, which reached the published persons table.
    arabic = """{| class="wikitable"
! المنصب !! الوزير
|-
| وزير الشؤون الدينية || شاغر
|-
| وزير الداخلية || خالد النوري
|}"""
    rows_ar = parse_tables(arabic)
    assert [r["person_name"] for r in rows_ar] == ["خالد النوري"]


def test_line_breaks_separate_concatenated_portfolios():
    """A minister holding two portfolios has them joined by <br>, not nothing.

    Stripping the tag welded them into "...du CommerceMinistre de
    l'Industrie", which matches no alias and falls into `other`.
    """
    rows = parse_tables(MECHICHI_TABLE)
    dual = [r for r in rows if r["person_name"] == "Mohamed Bousaïd"][0]
    assert "CommerceMinistre" not in dual["raw_title"]
    assert "Commerce" in dual["raw_title"] and "Industrie" in dual["raw_title"]


def test_party_column_survives_the_span():
    rows = parse_tables(MECHICHI_TABLE)
    parties = {r["person_name"]: r["party"] for r in rows}
    assert parties["Ridha Gharsallaoui"] == "Indépendant"


def test_restated_header_rows_are_not_ministers():
    """Long tables repeat their header, sometimes written with | not !.

    Position cannot tell such a row from data, so it is recognised by content.
    Left in, the Arabic for "Name" became a minister called الاسم - and a
    search for that person's biography then matched the article on the
    grammatical noun.
    """
    table = """{| class="wikitable"
! المنصب !! الوزير
|-
| وزير الداخلية || خالد النوري
|-
| الوظيفة || الاسم
|-
| وزير المالية || سهام البوغديري
|}"""
    names = [r["person_name"] for r in parse_tables(table)]
    assert names == ["خالد النوري", "سهام البوغديري"]


def test_search_titles_rejects_namesakes():
    """The search engine ranks by relevance; identity is decided by the title.

    Querying Arabic Wikipedia for "سمير عبيد" returns "سمير العبيدي" and
    "سميرة خميس عبيد" above any exact match. Accepting the top hit would
    attach another person's biography.
    """
    from govtn.sources.biographies import SEARCH_ACCEPT, search_titles

    class FakeFetcher:
        def __init__(self, results):
            self.results = results

        def get_json(self, url, params=None, **kwargs):
            term = (params or {}).get("srsearch")
            return {"query": {"search": [{"title": t}
                                          for t in self.results.get(term, [])]}}

    fetcher = FakeFetcher({
        "سمير عبيد": ["سمير العبيدي", "سميرة خميس عبيد"],
        "حبيب عبيد": ["الحبيب عبيد", "نبيلة عبيد"],
        "منير بن رجيبة": ["حكومة أحمد الحشاني"],
    })
    found = search_titles(["سمير عبيد", "حبيب عبيد", "منير بن رجيبة"],
                          fetcher, "ar", threshold=SEARCH_ACCEPT)
    # The definite article differs; the person does not.
    assert found == {"حبيب عبيد": "الحبيب عبيد"}


def test_section_labels_spanning_a_row_are_not_ministers():
    """Arabic rosters group members under headings inside the table.

    "الوزراء التونسيون" / "الوزراء الفرنسيون" (the Tunisian / the French
    ministers) separate sections of the protectorate cabinets. Where the
    heading is not marked up as a spanned cell it lands in every column, and
    was harvested as a minister holding an office named after himself - one
    record accumulating eleven appointments across five cabinets.
    """
    table = """{| class="wikitable"
! المنصب !! الوزير
|-
| الوزراء التونسيون || الوزراء التونسيون
|-
| وزير الداخلية || خالد النوري
|}"""
    assert [r["person_name"] for r in parse_tables(table)] == ["خالد النوري"]


def test_prose_in_a_name_column_is_rejected():
    """One article explains in a table cell how ministers are appointed."""
    sentence = ("الوزراء يقترحهم رئيس الحكومة وعددهم متغير حسب الوزارات "
                "الموجودة وزير الدفاع ووزير الخارجية يتم تعيينهم بعد التشاور")
    table = f"""{{| class="wikitable"
! المنصب !! الوزير
|-
| مجلس الوزراء || {sentence}
|-
| وزير الداخلية || خالد النوري
|}}"""
    assert [r["person_name"] for r in parse_tables(table)] == ["خالد النوري"]


def test_descriptive_bullets_are_not_roster_lines():
    """The list parser reached prose the table parser never saw.

    "Gouvernement de la Tunisie" describes the institution rather than listing
    a cabinet; its bullets define the offices. The definition was harvested as
    the minister and the defined term as the portfolio.
    """
    wikitext = (
        "* les ministres : ils sont d'un nombre variable en fonction des "
        "ministères qu'ils sont amenés à diriger ;\n"
        "* Ministre de l'Intérieur : [[Taïeb Mehiri]]\n"
    )
    assert [r["person_name"] for r in parse_lists(wikitext)] == ["Taïeb Mehiri"]


def test_prose_in_the_office_cell_is_rejected_but_real_titles_survive():
    """Both halves of this guard are load-bearing.

    An Arabic article explains in a table cell how ministers are appointed,
    with "الوزراء" ("the ministers") as the holder. Length alone would also
    reject a genuine dual portfolio, which runs to 125 characters; a full stop
    alone would reject "Secr. d'État au Plan et aux Finances".
    """
    from govtn.sources.wikipedia import _implausible_person

    prose = ("الوزراء يقترحهم رئيس الحكومة وعددهم متغير حسب الوزارات الموجودة. "
             "وزير الدفاع ووزير الخارجية يتم تعيينهم بعد التشاور من رئيس الوزراء")
    assert _implausible_person("الوزراء", prose)

    dual = ("Ministre du Commerce et du Développement des exportations / "
            "Ministre de l'Industrie, de l'Énergie et des Mines (intérim)")
    assert len(dual) > 90
    assert not _implausible_person("Mohamed Bousaïd", dual)
    assert not _implausible_person("Ahmed Ben Salah",
                                   "Secr. d'État au Plan et aux Finances")
