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
