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
    "الحقيبة", "المنصب", "الخطة",
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
_NOT_A_VALUE = re.compile(r"^(\d+\s*px|\d+|-|—|n/?a)$", re.IGNORECASE)

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
    cfg = config.sources()["wikipedia"]
    titles: list[str] = []
    for finder, arg in (
        (list_template_links, cfg["index_template"]),
        (list_category_members, cfg["index_category"]),
    ):
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


def _split_row(row: str) -> list[str]:
    """Split one wikitable row into cells.

    Cells may be written one per line (`| value`) or inline (`| a || b`), and
    a single article mixes both. Splitting has to handle each.
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
        for part in parts:
            # Drop cell attributes ("colspan=2 | value") but not wikilink pipes.
            if re.match(r"^[^\[\]{}]*=[^|]*\|(?!\|)", part):
                part = part.split("|", 1)[1]
            cells.append(part.strip())
    return cells


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


def parse_tables(wikitext: str) -> list[dict[str, Any]]:
    """Extract roster rows from every wikitable in the article."""
    rows: list[dict[str, Any]] = []
    for table in re.findall(r"\{\|.*?\n\|\}", wikitext, flags=re.DOTALL):
        chunks = re.split(r"\n\|-+", table)
        roles: dict[str, int] = {}
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
                    continue
                # Two-column tables without headers are the common minimal
                # case: assume portfolio then officeholder.
                if len(texts) == 2 and any(texts):
                    roles = {"portfolio": 0, "person": 1}
                else:
                    continue
            if max(roles.values()) >= len(cells_raw):
                continue
            portfolio = texts[roles["portfolio"]]
            person = texts[roles["person"]]
            if not portfolio or not person:
                continue
            if _SKIP_ROW.match(normalize_text(portfolio)):
                continue
            # Image sizes ("60px") and bare seat counts come from picture and
            # summary columns, not from roster columns.
            if _NOT_A_VALUE.match(portfolio.strip()) or _NOT_A_VALUE.match(person.strip()):
                continue
            links = _cell_links(cells_raw[roles["person"]])
            rows.append({
                "raw_title": portfolio,
                "person_name": person,
                "person_wikilink": links[0] if links else None,
                "party": texts[roles["party"]] if "party" in roles and roles["party"] < len(texts) else None,
                "date_note": texts[roles["date"]] if "date" in roles and roles["date"] < len(texts) else None,
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
            log.info("[%s] %d titles resolved via langlinks", lang, len(mapping))
            if not mapping:                      # fall back to this edition's own index
                titles = discover_cabinet_articles(fetcher, lang)
            else:
                titles = list(mapping)
                canonical = mapping
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
