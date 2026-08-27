"""Wikipedia cabinet-roster harvester.

Wikidata's P39 coverage of Tunisian cabinets is thin before 1987 and its
tenure qualifiers are frequently absent. The French Wikipedia "Gouvernement X"
articles, by contrast, carry near-complete ministerial rosters back to 1956.
This module turns those articles into (cabinet, portfolio, person) rows.

Two roster layouts occur in these articles and both must be handled:

  1. wikitable, with a portfolio column and an officeholder column whose
     headers vary ("Portefeuille"/"Fonction"/"Poste"/"Ministère" against
     "Titulaire"/"Ministre"/"Nom"/"Identité");
  2. plain bullet lists of the form
     `* Ministre de l'Intérieur : [[Taïeb Mehiri]]`.

Articles are fetched as wikitext rather than rendered HTML. Wikitext keeps
the `[[wikilink]]` targets intact, and those targets are what let a roster row
be resolved to a Wikidata QID through sitelinks - a far more reliable join
than the displayed name string.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Iterable

import mwparserfromhell

from .. import config
from ..http import Fetcher
from ..normalize import normalize_text, parse_date

log = logging.getLogger(__name__)

# Column headers seen in Tunisian cabinet tables, normalised.
PORTFOLIO_HEADERS = (
    "portefeuille", "fonction", "poste", "ministere", "departement",
    "charge", "attribution", "qualite", "office", "portfolio", "الوزارة",
    "الحقيبة", "المنصب", "الخطة", "الوظيفة", "الصفة",
)
PERSON_HEADERS = (
    "titulaire", "ministre", "nom", "identite", "membre", "personnalite",
    "holder", "minister", "name", "الاسم", "صاحب", "الوزير",
)
PARTY_HEADERS = ("parti", "appartenance", "etiquette", "party", "الحزب", "الانتماء")
DATE_HEADERS = ("date", "periode", "depuis", "entree", "sortie", "التاريخ", "الفترة")
IMAGE_HEADERS = ("image", "photo", "portrait", "صورة")

# Header keywords are compared against text that has been through
# `normalize_text`, which folds Arabic orthography (ة -> ه, أ -> ا). The
# constants above are written in natural orthography, so they must be folded
# too - otherwise no Arabic header ever matches, header detection silently
# falls back to guessing columns, and image or party columns get read as the
# portfolio ("60px", "نداء تونس").
PORTFOLIO_HEADERS = tuple(normalize_text(h) for h in PORTFOLIO_HEADERS)
PERSON_HEADERS = tuple(normalize_text(h) for h in PERSON_HEADERS)
PARTY_HEADERS = tuple(normalize_text(h) for h in PARTY_HEADERS)
DATE_HEADERS = tuple(normalize_text(h) for h in DATE_HEADERS)
IMAGE_HEADERS = tuple(normalize_text(h) for h in IMAGE_HEADERS)

# Values that are never an officeholder or an office.
# Cell contents that are placeholders rather than values. A cell reduced to
# punctuation is the residue of markup the parser stripped, not a name.
_NOT_A_VALUE = re.compile(
    r"^(\d+\s*px|\d+|[-—|/.,:;]+|n/?a|"
    # A post recorded as unfilled. Harvested as a person, "Poste vacant" and
    # its Arabic equivalent become ministers who never existed.
    r"poste vacant|vacant|vacance|shagher|"
    r"شاغر|شاغرة|منصب شاغر)$",
    re.IGNORECASE)

# A person name longer than this is prose, not a name. Set well clear of the
# longest real names in the data - full Arabic patronymic chains run to about
# forty characters and six tokens.
_MAX_NAME_CHARS = 90
_MAX_NAME_WORDS = 12

# A full stop with running text after it. Only consulted for cells already
# longer than a title has any reason to be; on its own it fires on the
# abbreviation in "Secr. d'État au Plan et aux Finances".
_SENTENCE_BREAK = re.compile(r"[.؟!]\s+\S+\s+\S+")

# Rows that are section separators rather than officeholders.
_SKIP_ROW = re.compile(
    r"^(ministres?|secretaires? d'etat|composition|remaniement|"
    r"membres? du gouvernement|notes?|references?)\s*$"
)


def _fetcher(offline: bool = False) -> Fetcher:
    cfg = config.sources()["wikipedia"]
    return Fetcher(
        source="wikipedia",
        rate_limit=cfg["rate_limit_seconds"],
        timeout=cfg["timeout_seconds"],
        offline=offline,
    )


def _api(lang: str) -> str:
    for edition in config.sources()["wikipedia"]["editions"]:
        if edition["lang"] == lang:
            return edition["api"]
    raise KeyError(f"no Wikipedia edition configured for {lang!r}")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def list_template_links(template: str, fetcher: Fetcher, lang: str = "fr") -> list[str]:
    """Article titles linked from a navigation template.

    `Modèle:Palette Gouvernements de la Tunisie` is the canonical index of
    cabinet articles on the French Wikipedia; following its links is more
    complete and less brittle than guessing article titles from the head of
    government's name.
    """
    payload = fetcher.get_json(_api(lang), {
        "action": "query", "format": "json", "formatversion": "2",
        "titles": template, "prop": "links", "plnamespace": "0", "pllimit": "max",
    })
    pages = payload.get("query", {}).get("pages", [])
    titles: list[str] = []
    for page in pages:
        for link in page.get("links", []):
            titles.append(link["title"])
    return titles


def list_category_members(category: str, fetcher: Fetcher, lang: str = "fr") -> list[str]:
    """Article titles in a category, used as a second discovery channel."""
    titles: list[str] = []
    params = {
        "action": "query", "format": "json", "formatversion": "2",
        "list": "categorymembers", "cmtitle": category,
        "cmnamespace": "0", "cmlimit": "max",
    }
    while True:
        payload = fetcher.get_json(_api(lang), params)
        titles.extend(m["title"] for m in payload.get("query", {}).get("categorymembers", []))
        cont = payload.get("continue")
        if not cont:
            break
        params = {**params, **cont}
    return titles


def langlinked_titles(
    titles: list[str], fetcher: Fetcher, target_lang: str, source_lang: str = "fr"
) -> dict[str, str]:
    """Titles of the same articles in another language edition.

    Discovery for non-French editions goes through langlinks rather than that
    edition's own navigation template. Guessing at the Arabic template and
    category names would be brittle and, when wrong, silently yields zero
    articles - which is exactly what happened before this existed.
    """
    # target title -> source-language title. The mapping, not just the list,
    # is what lets the two editions' versions of one cabinet share a single
    # cabinet_id. Without it "Gouvernement Karoui" and "حكومة حامد القروي"
    # become two separate cabinets and every minister in them is counted twice.
    found: dict[str, str] = {}
    for title in titles:
        try:
            payload = fetcher.get_json(_api(source_lang), {
                "action": "query", "format": "json", "formatversion": "2",
                "titles": title, "prop": "langlinks",
                "lllang": target_lang, "lllimit": "max", "redirects": "1",
            })
        except Exception as exc:
            log.warning("langlinks failed for %s: %s", title, exc)
            continue
        for page in payload.get("query", {}).get("pages", []):
            for link in page.get("langlinks", []) or []:
                found[link["title"]] = page.get("title", title)
    return found


def discover_cabinet_articles(fetcher: Fetcher, lang: str = "fr") -> list[str]:
    """Union of the navigation-template and category channels.

    Both are used because each misses articles the other catches: the palette
    omits cabinets nobody has added to it, the category omits cabinets whose
    article was never categorised.
    """
    edition = next(
        (e for e in config.sources()["wikipedia"]["editions"] if e["lang"] == lang), {}
    )
    titles: list[str] = []
    channels = []
    if edition.get("index_template"):
        channels.append((list_template_links, edition["index_template"]))
    if edition.get("index_category"):
        channels.append((list_category_members, edition["index_category"]))
    for finder, arg in channels:
        try:
            found = finder(arg, fetcher, lang)
            log.info("%s -> %d titles", arg, len(found))
            titles.extend(found)
        except Exception as exc:                      # one channel failing is survivable
            log.warning("discovery via %s failed: %s", arg, exc)

    seen, out = set(), []
    for title in titles:
        # Keep only cabinet articles, not ministries or biographies that the
        # palette also links to.
        if not re.search(r"gouvernement|حكومة|cabinet", title, re.IGNORECASE):
            continue
        if title not in seen:
            seen.add(title)
            out.append(title)
    return out


def fetch_wikitext(
    title: str, fetcher: Fetcher, lang: str = "fr"
) -> tuple[str, str] | tuple[None, None]:
    """Raw wikitext of an article, with the title MediaWiki resolved it to.

    The resolved title matters: "Gouvernement Jebali" and "Gouvernement Hamadi
    Jebali" are the same article behind a redirect, and harvesting both records
    every one of that cabinet's ministers twice - inflating cabinet size and
    manufacturing duplicate co-membership ties. Callers must de-duplicate on
    the resolved title, not on the title they asked for.
    """
    payload = fetcher.get_json(_api(lang), {
        "action": "query", "format": "json", "formatversion": "2",
        "titles": title, "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "redirects": "1",
    })
    for page in payload.get("query", {}).get("pages", []):
        if page.get("missing"):
            return None, None
        revisions = page.get("revisions") or []
        if revisions:
            return revisions[0]["slots"]["main"]["content"], page.get("title", title)
    return None, None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _cell_text(cell: str) -> str:
    """Strip wiki markup from a table cell, keeping the visible text."""
    # Footnotes and comments must be removed WHOLE. Stripping only the tags
    # would splice the footnote's prose into the officeholder's name
    # ("Chedli KlibiNote de bas de page").
    cell = re.sub(r"<ref[^>]*/>", " ", cell)
    cell = re.sub(r"<ref[^>]*>.*?</ref>", " ", cell, flags=re.DOTALL | re.IGNORECASE)
    cell = re.sub(r"<!--.*?-->", " ", cell, flags=re.DOTALL)
    # A line break separates two things; removing it welds them together.
    # Without this, a minister holding two portfolios came out as
    # "Ministre du Commerce et du Developpement des exportationsMinistre de
    # l'Industrie", which matches no alias and lands in `other`.
    cell = re.sub(r"<\s*br\s*/?\s*>", " / ", cell, flags=re.IGNORECASE)
    code = mwparserfromhell.parse(cell)
    for template in code.filter_templates():
        # Flag/date templates carry no roster information; drop them so they
        # do not leak template names into the extracted strings.
        try:
            code.remove(template)
        except ValueError:
            pass
    text = code.strip_code()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[!|]+", "", text)
    text = re.sub(r"\{\{|\}\}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_DATE_TEMPLATE = re.compile(r"\{\{\s*(?:date|Date)\s*\|([^}]*)\}\}")


def _caption_text(caption: str) -> str:
    """Caption text with date templates expanded to their arguments.

    `{{date|27 septembre 1989}}` carries the value, so it must be unwrapped
    rather than removed. Template arguments are pipe-separated and may carry
    named parameters, which are dropped.
    """
    def expand(match: re.Match) -> str:
        parts = [p.strip() for p in match.group(1).split("|") if "=" not in p]
        return " ".join(parts)

    text = _DATE_TEMPLATE.sub(expand, caption)
    text = re.sub(r"\{\{[^}]*\}\}", " ", text)      # any remaining templates
    text = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", text)
    return re.sub(r"\s+", " ", text).strip()


def _cell_links(cell: str) -> list[str]:
    """Wikilink targets in a cell - the reliable join key to Wikidata."""
    code = mwparserfromhell.parse(cell)
    out = []
    for link in code.filter_wikilinks():
        target = str(link.title).strip()
        if ":" in target.split("|")[0] and not target.startswith(":"):
            continue                                   # File:, Catégorie:, ...
        out.append(target.lstrip(":"))
    return out


# `colspan=3`, `colspan="3"`. A spanned cell occupies that many columns, so
# every column to its right shifts unless the span is expanded.
_COLSPAN = re.compile(r"\bcolspan\s*=\s*[\"\']?(\d{1,2})", re.IGNORECASE)


def _split_row(row: str) -> list[str]:
    """Split one wikitable row into cells, expanding `colspan`.

    Cells may be written one per line (`| value`) or inline (`| a || b`), and
    a single article mixes both. Splitting has to handle each.

    COLSPAN IS EXPANDED INTO PLACEHOLDER CELLS. A header written
    `! colspan=2 | Titulaire` describes two columns, and the data rows beneath
    it supply two. Emitting one header cell makes the header shorter than its
    rows, so every column index derived from the header points one place to
    the left. In the FR "Gouvernement Mechichi" article that put the person
    column on a party-colour swatch, and sixteen ministers were harvested with
    the literal name "|" - a person record per office, all of them junk, all in
    the least-documented period of the dataset.
    """
    cells: list[str] = []
    for line in row.split("\n"):
        line = line.strip()
        if not line or line.startswith("|-") or line.startswith("{|") or line.startswith("|}"):
            continue
        if line.startswith("|+"):
            # Table CAPTION, not a cell. Treated as one it becomes phantom
            # column 0 of the header row, shifting every column index by one
            # against the data rows - which silently emptied whole cabinets
            # ("Gouvernement Hamed Karoui" parsed to zero members).
            continue
        if line.startswith("!"):
            parts = re.split(r"!!", line.lstrip("!"))
        elif line.startswith("|"):
            parts = re.split(r"\|\|", line.lstrip("|"))
        else:
            if cells:                                   # continuation of previous cell
                cells[-1] += " " + line
            continue
        is_header = line.startswith("!")
        for part in parts:
            attributes, part = _split_attributes(part)
            part = part.strip()
            cells.append(part)
            # The cell already occupies one column; add the rest of its span.
            # A spanned HEADER label describes each column it covers, so it is
            # repeated - that is what lets a role find the real value inside
            # the span. A spanned DATA cell gets blanks: repeating a value
            # would invent duplicates.
            span = _COLSPAN.search(attributes)
            if span:
                extra = max(0, min(int(span.group(1)), 12) - 1)
                cells.extend([part if is_header else ""] * extra)
    return cells


def _split_attributes(part: str) -> tuple[str, str]:
    """Separate a cell's HTML attributes from its content.

    MediaWiki reads everything before the first pipe as attributes, but only
    when that pipe is at the top level: a pipe inside `[[...]]`, `{{...}}` or
    `<!--...-->` belongs to the link, template or comment. Scanning for the
    first *unnested* pipe is what distinguishes
    `| {{Infobox .../couleurs|Autre}} |` - a swatch template followed by an
    empty content cell - from a wikilink whose pipe separates target and label.
    Returns ("", part) when the cell carries no attributes.
    """
    depth_brace = depth_bracket = 0
    index = 0
    while index < len(part):
        pair = part[index:index + 2]
        if pair == "{{":
            depth_brace += 1; index += 2; continue
        if pair == "}}":
            depth_brace = max(0, depth_brace - 1); index += 2; continue
        if pair == "[[":
            depth_bracket += 1; index += 2; continue
        if pair == "]]":
            depth_bracket = max(0, depth_bracket - 1); index += 2; continue
        if part[index] == "|" and not depth_brace and not depth_bracket:
            head, tail = part[:index], part[index + 1:]
            # Attributes are `key=value` pairs, optionally preceded by a
            # template that renders a background colour. Anything else with a
            # pipe in it is content that happens to contain one.
            if "=" in head or _TEMPLATE_ONLY.fullmatch(head.strip()):
                return head, tail
            return "", part
        index += 1
    return "", part


_TEMPLATE_ONLY = re.compile(r"(?:\{\{[^{}]*\}\}\s*)+")


def _implausible_person(person: str, portfolio: str) -> bool:
    """True when this pairing cannot be an officeholder and an office.

    Shared by the table and list parsers, because the same two failures reach
    both:

    A SECTION LABEL that lands in every column. Arabic rosters group members
    under headings like "الوزراء التونسيون" / "الوزراء الفرنسيون" (the Tunisian
    / the French ministers); where the heading is not marked up as a spanned
    cell it fills both columns, and was harvested as a minister holding an
    office named after himself - one record collecting eleven appointments
    across five cabinets. No minister is named after the post they hold.

    PROSE. Descriptive articles define the offices rather than listing holders:
    "Gouvernement de la Tunisie" has bullets reading
    "les ministres : ils sont d'un nombre variable...". The definition became
    the minister and the defined term became the portfolio.
    """
    if normalize_text(person) == normalize_text(portfolio):
        return True
    if len(person) > _MAX_NAME_CHARS or len(person.split()) > _MAX_NAME_WORDS:
        return True
    # Prose in the OFFICE cell instead, with a plural common noun as the
    # holder: "الوزراء" ("the ministers") against a sentence explaining how
    # they are appointed. Neither test alone works - a genuine dual portfolio
    # runs to 125 characters, and "Secr. d'État au Plan et aux Finances"
    # contains a full stop - so both must hold.
    return len(portfolio) > _MAX_NAME_CHARS and bool(_SENTENCE_BREAK.search(portfolio))


def _classify_headers(cells: list[str]) -> dict[str, int]:
    """Map header cells to roles by keyword, returning column indices."""
    roles: dict[str, int] = {}
    for index, cell in enumerate(cells):
        text = normalize_text(cell)
        if not text:
            continue
        if any(k in text for k in IMAGE_HEADERS):
            continue                       # picture column, never a roster field
        if "portfolio" not in roles and any(k in text for k in PORTFOLIO_HEADERS):
            roles["portfolio"] = index
        elif "person" not in roles and any(k in text for k in PERSON_HEADERS):
            roles["person"] = index
        elif "party" not in roles and any(k in text for k in PARTY_HEADERS):
            roles["party"] = index
        elif "date" not in roles and any(k in text for k in DATE_HEADERS):
            roles["date"] = index
    return roles


def _resolve(role: str, roles: dict[str, int], headers: list[str],
             texts: list[str]) -> int | None:
    """Index of the cell that actually holds `role`'s value in this row.

    A `colspan` header covers several columns and only one of them carries the
    value. "Titulaire" spanning two columns in the FR cabinet tables covers a
    party-colour swatch and then the name; the swatch is empty once its
    template is stripped. Walk right through the columns the same header label
    covers and take the first that is not empty.
    """
    if role not in roles:
        return None
    start = roles[role]
    if start >= len(texts):
        return None
    if texts[start]:
        return start
    label = headers[start] if start < len(headers) else ""
    index = start + 1
    while index < len(texts) and index < len(headers) and headers[index] == label:
        if texts[index]:
            return index
        index += 1
    return start


def parse_tables(wikitext: str) -> list[dict[str, Any]]:
    """Extract roster rows from every wikitable in the article."""
    rows: list[dict[str, Any]] = []
    for table in re.findall(r"\{\|.*?\n\|\}", wikitext, flags=re.DOTALL):
        # The caption dates the table, and each table is one composition or
        # one reshuffle: "Composition le 27 septembre 1989", "Postes remaniés
        # le 3 mars 1990". That is a real, individual-level start date for
        # every row in it - far better than inheriting the whole cabinet's
        # span, which for a ten-year government is useless as a tenure.
        table_date = None
        caption = re.search(r"\n\|\+([^\n]*)", table)
        if caption:
            # NOT _cell_text here: that removes templates, and the date IS a
            # template ({{date|27 septembre 1989}}). Stripping it left
            # "Composition le" and the date was lost for every captioned
            # table in the corpus.
            parsed_caption = parse_date(_caption_text(caption.group(1)))
            if parsed_caption.value:
                table_date = {
                    "date": parsed_caption.value.isoformat(),
                    "precision": parsed_caption.precision,
                    "caption": _cell_text(caption.group(1))[:80],
                }

        chunks = re.split(r"\n\|-+", table)
        roles: dict[str, int] = {}
        headers: list[str] = []
        for chunk in chunks:
            cells_raw = _split_row(chunk)
            if not cells_raw:
                continue
            texts = [_cell_text(c) for c in cells_raw]
            if not roles:
                candidate = _classify_headers(texts)
                # A usable header needs both a portfolio and a person column.
                if "portfolio" in candidate and "person" in candidate:
                    roles = candidate
                    headers = texts
                    continue
                # Two-column tables without headers are the common minimal
                # case: assume portfolio then officeholder.
                if len(texts) == 2 and any(texts):
                    roles = {"portfolio": 0, "person": 1}
                else:
                    continue
            if max(roles.values()) >= len(cells_raw):
                continue
            portfolio_at = _resolve("portfolio", roles, headers, texts)
            person_at = _resolve("person", roles, headers, texts)
            if portfolio_at is None or person_at is None:
                continue
            portfolio = texts[portfolio_at]
            person = texts[person_at]
            if not portfolio or not person:
                continue
            if _SKIP_ROW.match(normalize_text(portfolio)):
                continue
            # A header restated mid-table. Long wikitables repeat their header
            # every so often, and a repeat written with "|" instead of "!" is
            # indistinguishable from data by position alone. Recognise it by
            # content: both cells naming their own column means this row
            # describes the table, not a minister. Left in, the Arabic word for
            # "Name" became a person, and then a search for a biography of that
            # person matched the grammar article for "noun".
            if (any(k in normalize_text(person) for k in PERSON_HEADERS)
                    and any(k in normalize_text(portfolio) for k in PORTFOLIO_HEADERS)):
                continue
            if _implausible_person(person, portfolio):
                continue
            # Image sizes ("60px") and bare seat counts come from picture and
            # summary columns, not from roster columns.
            if _NOT_A_VALUE.match(portfolio.strip()) or _NOT_A_VALUE.match(person.strip()):
                continue
            links = _cell_links(cells_raw[person_at])
            rows.append({
                "raw_title": portfolio,
                "person_name": person,
                "person_wikilink": links[0] if links else None,
                "party": texts[roles["party"]] if "party" in roles and roles["party"] < len(texts) else None,
                "date_note": texts[roles["date"]] if "date" in roles and roles["date"] < len(texts) else None,
                "table_date": (table_date or {}).get("date"),
                "table_date_precision": (table_date or {}).get("precision"),
                "table_caption": (table_date or {}).get("caption"),
                "layout": "table",
            })
    return rows


_LIST_ROW = re.compile(r"^\*+\s*(?P<left>[^:：]{3,120}?)\s*[:：]\s*(?P<right>.+)$")

# Office keywords, used to work out which side of the colon is the portfolio.
_OFFICE_WORD = re.compile(
    r"ministre|secretaire|chef\b|president|grand vizir|vizir|directeur|"
    r"gouverneur|وزير|كاتب|رئيس"
)


def parse_lists(wikitext: str) -> list[dict[str, Any]]:
    """Extract roster rows from bullet lists (`* Ministre de X : [[Y]]`)."""
    rows: list[dict[str, Any]] = []
    for line in wikitext.split("\n"):
        line = line.strip()
        if not line.startswith("*"):
            continue
        match = _LIST_ROW.match(line)
        if not match:
            continue
        left_cell, right_cell = match.group("left"), match.group("right")
        left, right = _cell_text(left_cell), _cell_text(right_cell)
        if not left or not right:
            continue

        # BOTH orders occur. Post-1956 articles write "Ministre de X : Person";
        # the protectorate-era ones write "Person : grand vizir". Decide by
        # which side names an office rather than assuming a fixed order -
        # assuming one silently drops every article using the other.
        left_is_office = bool(_OFFICE_WORD.search(normalize_text(left)))
        right_is_office = bool(_OFFICE_WORD.search(normalize_text(right)))
        if left_is_office and not right_is_office:
            raw_title, person, person_cell = left, right, right_cell
        elif right_is_office and not left_is_office:
            raw_title, person, person_cell = right, left, left_cell
        else:
            # Neither side, or both, look like an office: not a roster line.
            continue
        # List items carry the sentence punctuation of the surrounding prose
        # ("grand vizir ;"); it is not part of the office name.
        raw_title = re.sub(r"[\s;,.]+$", "", raw_title)
        if _implausible_person(person, raw_title):
            continue
        links = _cell_links(person_cell)
        rows.append({
            "raw_title": raw_title,
            "person_name": person,
            "person_wikilink": links[0] if links else None,
            "party": None,
            "date_note": None,
            "layout": "list",
        })
    return rows


def parse_infobox_dates(wikitext: str) -> dict[str, Any]:
    """Formation / end dates from the article's infobox."""
    out: dict[str, Any] = {}
    code = mwparserfromhell.parse(wikitext)
    for template in code.filter_templates():
        name = normalize_text(str(template.name))
        if "gouvernement" not in name and "infobox" not in name:
            continue
        for param in template.params:
            key = normalize_text(str(param.name))
            value = _cell_text(str(param.value))
            if not value:
                continue
            if key in {"formation", "date de formation", "debut", "entree en fonction"}:
                out["start"] = value
            elif key in {"fin", "date de dissolution", "dissolution", "sortie"}:
                out["end"] = value
            elif key in {"legislature", "president", "chef", "dirigeant", "chef du gouvernement"}:
                out[key.replace(" ", "_")] = value
    for bound in ("start", "end"):
        if bound in out:
            parsed = parse_date(out[bound])
            out[f"{bound}_date"] = parsed.value.isoformat() if parsed.value else None
            out[f"{bound}_precision"] = parsed.precision
    return out


def parse_cabinet_article(title: str, wikitext: str, lang: str = "fr") -> dict[str, Any]:
    """Parse one cabinet article into a roster record.

    Table rows are preferred over list rows: when an article has both, the
    lists are usually a prose summary duplicating the table. Lists are used
    only when no usable table was found.
    """
    table_rows = parse_tables(wikitext)
    list_rows = parse_lists(wikitext)
    members = table_rows if table_rows else list_rows

    seen: set[tuple[str, str]] = set()
    deduped = []
    for row in members:
        key = (normalize_text(row["raw_title"]), normalize_text(row["person_name"]))
        if key in seen:
            continue
        seen.add(key)
        row["cabinet_article"] = title
        row["lang"] = lang
        deduped.append(row)

    return {
        "article": title,
        "lang": lang,
        "infobox": parse_infobox_dates(wikitext),
        "n_table_rows": len(table_rows),
        "n_list_rows": len(list_rows),
        "members": deduped,
    }


# ---------------------------------------------------------------------------

def harvest(*, offline: bool = False, langs: Iterable[str] = ("fr",)) -> list[dict[str, Any]]:
    """Discover and parse every Tunisian cabinet article."""
    fetcher = _fetcher(offline)
    interim = config.paths().ensure().interim
    cabinets: list[dict[str, Any]] = []

    french_titles: list[str] = []
    for lang in langs:
        canonical: dict[str, str] = {}
        if lang == "fr":
            titles = discover_cabinet_articles(fetcher, lang)
            french_titles = list(titles)
        else:
            mapping = langlinked_titles(french_titles, fetcher, lang)
            own = discover_cabinet_articles(fetcher, lang)
            log.info(
                "[%s] %d titles via langlinks, %d via this edition's own index",
                lang, len(mapping), len(own),
            )
            # UNION, not fallback. A government with an Arabic article and no
            # French one has no langlink to follow, and treating the local
            # index as a mere fallback meant it was never consulted whenever
            # langlinks returned anything at all.
            canonical = mapping
            titles = list(mapping) + [t for t in own if t not in mapping]
        # Seeds from the curated spine catch anything discovery missed.
        seeds = [s.get(f"wikipedia_{lang}") for s in config.cabinets()["spells"]]
        for seed in seeds:
            if seed and seed not in titles:
                titles.append(seed)
        log.info("[%s] %d cabinet articles to parse", lang, len(titles))

        seen_articles: set[str] = set()
        for title in titles:
            try:
                wikitext, resolved = fetch_wikitext(title, fetcher, lang)
            except Exception as exc:
                log.warning("fetch failed for %s: %s", title, exc)
                continue
            if not wikitext:
                log.info("no article: %s", title)
                continue
            if resolved in seen_articles:
                log.debug("%s redirects to %s, already harvested", title, resolved)
                continue
            seen_articles.add(resolved)
            record = parse_cabinet_article(resolved, wikitext, lang)
            record["requested_as"] = sorted({title, resolved})
            # The French title is the canonical identity of the cabinet, so
            # the same government harvested in two languages stays one cabinet.
            record["canonical_article"] = canonical.get(title, resolved)
            for member in record["members"]:
                member["canonical_article"] = record["canonical_article"]
            log.info("%-55s %3d members", resolved[:55], len(record["members"]))
            cabinets.append(record)

    path = interim / "wikipedia_cabinets.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(cabinets, fh, indent=1, ensure_ascii=False)
    log.info("wrote %s (%d cabinets, %d member rows)",
             path, len(cabinets), sum(len(c["members"]) for c in cabinets))
    fetcher.flush()
    return cabinets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--langs", default="fr", help="comma-separated, e.g. fr,ar")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    harvest(offline=args.offline, langs=tuple(args.langs.split(",")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
