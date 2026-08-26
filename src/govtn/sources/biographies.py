"""Minister biography harvester (Wikipedia categories and infoboxes).

The cabinet rosters give offices; they say nothing about who the officeholder
was. This module fills that in from each minister's own biography article, and
it is what lifts education coverage out of the single digits.

WHY CATEGORIES RATHER THAN PROSE
French Wikipedia categorises biographies with a controlled, highly regular
vocabulary that is far more reliable than parsing intro sentences:

    Catégorie:Naissance en août 1955          -> birth, month precision
    Catégorie:Naissance à Médenine            -> birthplace
    Catégorie:Élève du Collège Sadiki         -> education
    Catégorie:Personnalité du Mouvement Ennahdha  -> party
    Catégorie:Prisonnier politique tunisien   -> political imprisonment
    Catégorie:Ingénieure tunisienne           -> profession, and gender via the
                                                 feminine "-e" form

The Collège Sadiki and the Lycée Carnot cases are the point of the exercise:
a handful of schools supplied a large share of the post-independence
ministerial elite, and that is invisible without this layer.

Gender is inferred ONLY from unambiguous feminine grammatical forms and
explicit "Femme ..." categories, and is recorded as a separate
`gender_hint` field rather than overwriting Wikidata's P21.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Iterable

from .. import config
from ..http import Fetcher
from ..normalize import normalize_text, parse_date

log = logging.getLogger(__name__)

BATCH = 20          # titles per API request


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
    raise KeyError(lang)


# ---------------------------------------------------------------------------
# Category patterns (French)
# ---------------------------------------------------------------------------
# Written against the NORMALISED category name (accents stripped, lowercased),
# so "Élève du Collège Sadiki" is matched as "eleve du college sadiki".

_ARTICLE = r"(?:du |de la |de l'|des |de |d'|au |a l'|a la |a )"

FR_PATTERNS: dict[str, list[re.Pattern]] = {
    "birth": [re.compile(r"^naissance en (?:(\w+) )?(\d{4})$")],
    "birth_place": [re.compile(rf"^naissance a (.+)$")],
    "death": [re.compile(r"^deces en (?:(\w+) )?(\d{4})$")],
    "death_place": [re.compile(rf"^deces a (.+)$")],
    "education": [
        re.compile(rf"^eleve {_ARTICLE}(.+)$"),
        re.compile(rf"^etudiant[e]? {_ARTICLE}(.+)$"),
        re.compile(rf"^(?:eleve|diplome)[e]? {_ARTICLE}(.+)$"),
        re.compile(rf"^docteur {_ARTICLE}(.+)$"),
    ],
    "employer": [re.compile(rf"^(?:professeur|enseignant)[e]? a (?:l'|la |le )?(.+)$")],
    "party": [re.compile(rf"^personnalite {_ARTICLE}(.+)$")],
    # "Membre de l'Académie tunisienne..." is a learned-society membership, not
    # a party. Pooling the two made an academy look like the eighth-largest
    # party in Tunisia.
    "membership": [re.compile(rf"^membre {_ARTICLE}(.+)$")],
    "award": [re.compile(r"^(?:grand cordon|recipiendaire|commandeur|officier) (?:de )?l?'?(.+)$")],
}

# Categories that are themselves the signal, no capture needed.
FR_FLAGS: dict[str, re.Pattern] = {
    "political_prisoner": re.compile(r"^prisonnier politique|^personnalite emprisonnee"),
    "exile": re.compile(r"^exile|^refugie politique"),
    "trade_unionist": re.compile(r"syndicaliste"),
    "academic": re.compile(r"^universitaire|^professeur|^enseignant"),
    "military": re.compile(r"^militaire|^general |^colonel |^officier de l'armee"),
    "diplomat": re.compile(r"^diplomate|^ambassadeur"),
    "lawyer": re.compile(r"^avocat|^magistrat|^juriste"),
    "physician": re.compile(r"^medecin|^chirurgien"),
    "engineer": re.compile(r"^ingenieur"),
    "economist": re.compile(r"^economiste"),
    "journalist": re.compile(r"^journaliste"),
    "writer": re.compile(r"^ecrivain|^poete|^romancier"),
}

# Unambiguous feminine forms. French Wikipedia genders occupational categories,
# so "Ingénieure tunisienne" and "Femme politique" identify women reliably;
# the masculine form is the unmarked default and proves nothing on its own.
FR_FEMININE = re.compile(
    r"^femme |^pionniere |ingenieure|universitaire tunisienne|"
    r"femme politique|femme scientifique|femme de lettres|"
    r"^premiere ministre|avocate |medecin femme|professeure"
)

# ---------------------------------------------------------------------------
# Category patterns (Arabic)
# ---------------------------------------------------------------------------
# Matched against text folded by `normalize_text` (ة -> ه, أ -> ا), so the
# patterns are written in that folded orthography.
#
# THE HIJRI TRAP: Arabic Wikipedia tags a birth year twice, once Gregorian and
# once Hijri - "مواليد 1955" alongside "مواليد 1374 هـ". Matching the year
# without excluding the Hijri marker yields a birth year 580 years adrift, and
# it looks perfectly plausible in a table.

AR_PATTERNS: dict[str, list[re.Pattern]] = {
    "birth": [re.compile(r"^مواليد (\d{4})$")],          # bare year only: no هـ
    "birth_place": [
        re.compile(r"^مواليد في (.+)$"),
        re.compile(r"^اشخاص من (?:ولايه )?(.+)$"),
    ],
    "death": [re.compile(r"^وفيات (\d{4})$")],
    "education": [re.compile(r"^خريج(?:و|ات) (.+)$")],
    "party": [re.compile(r"^شخصيات (.+)$")],
}

AR_FLAGS: dict[str, re.Pattern] = {
    "political_prisoner": re.compile(r"ضحايا التعذيب|سجناء سياسيون|معتقلون"),
    "exile": re.compile(r"منفيون|لاجئون"),
    "academic": re.compile(r"^اكاديمي|^اساتذه جامع"),
    "military": re.compile(r"^عسكريون|^جنرالات"),
    "diplomat": re.compile(r"^دبلوماسيون|^سفراء"),
    "lawyer": re.compile(r"^محامون|^قضاه"),
    "physician": re.compile(r"^اطباء"),
    "engineer": re.compile(r"^مهندس"),
    "economist": re.compile(r"^اقتصاديون"),
    "journalist": re.compile(r"^صحفيون"),
}

# Arabic marks the feminine with a distinct plural form, which is an
# unambiguous gender signal: وزيرات (women ministers), سياسيات (women
# politicians), مهندسات (women engineers), رئيسات (women heads of).
AR_FEMININE = re.compile(
    r"^نساء |وزيرات|سياسيات|مهندسات|رئيسات|اكاديميات|طبيبات|محاميات|عالمات"
)

# Values the "شخصيات X" shape produces that are not parties.
_AR_NOT_A_PARTY = re.compile(r"^(الربيع العربي|الثوره|تونسيه|تونسيون)")

_MONTHS_FR = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}

# Category values that are not really an institution or a party.
_NOISE = re.compile(
    r"^(tunisie|tunisien|france|paris|xxe siecle|xxie siecle|"
    r"personnalite politique|homme politique|femme politique)\b"
)

# Values that the "Personnalité de X" category shape produces but which are not
# political parties: historical episodes, movements and learned societies.
_NOT_A_PARTY = re.compile(
    r"^(printemps arabe|revolution|mouvement national|academie|"
    r"guerre|resistance|decolonisation|societe|association|ordre |"
    r"franc-maconnerie|diaspora)"
)


def parse_categories(categories: Iterable[str], lang: str = "fr") -> dict[str, Any]:
    """Turn a biography's category list into structured fields."""
    if lang == "ar":
        return _parse_arabic(categories)
    out: dict[str, Any] = {
        "education_institutions": [],
        "parties": [],
        "awards": [],
        "employers": [],
        "memberships": [],
        "flags": [],
    }
    feminine = False

    for raw in categories:
        name = raw.split(":", 1)[-1]
        text = normalize_text(name)
        if not text:
            continue

        if FR_FEMININE.search(text):
            feminine = True

        for flag, pattern in FR_FLAGS.items():
            if pattern.search(text) and flag not in out["flags"]:
                out["flags"].append(flag)

        for field, patterns in FR_PATTERNS.items():
            for pattern in patterns:
                match = pattern.match(text)
                if not match:
                    continue
                if field in {"birth", "death"}:
                    month, year = match.groups()
                    if field in out:
                        break
                    number = _MONTHS_FR.get(month or "")
                    out[field] = f"{year}-{number:02d}-01" if number else f"{year}-01-01"
                    out[f"{field}_precision"] = "month" if number else "year"
                elif field in {"birth_place", "death_place"}:
                    out.setdefault(field, name.split("à", 1)[-1].strip())
                elif field == "education":
                    value = name.split(" ", 1)[-1]
                    if not _NOISE.match(normalize_text(value)):
                        out["education_institutions"].append(_strip_article(value))
                elif field == "employer":
                    out["employers"].append(_strip_article(name.split(" à ", 1)[-1]))
                elif field == "party":
                    value = _strip_article(name.split(" ", 1)[-1])
                    key = normalize_text(value)
                    if not _NOISE.match(key) and not _NOT_A_PARTY.match(key):
                        out["parties"].append(value)
                elif field == "membership":
                    value = _strip_article(name.split(" ", 1)[-1])
                    if not _NOISE.match(normalize_text(value)):
                        out["memberships"].append(value)
                elif field == "award":
                    out["awards"].append(name)
                break

    if feminine:
        out["gender_hint"] = "female"
    for key in ("education_institutions", "parties", "awards", "employers",
                "memberships"):
        out[key] = _dedupe(out[key])
    return out


def _parse_arabic(categories: Iterable[str]) -> dict[str, Any]:
    """Arabic-edition equivalent of :func:`parse_categories`."""
    out: dict[str, Any] = {
        "education_institutions": [], "parties": [], "awards": [],
        "employers": [], "memberships": [], "flags": [],
    }
    feminine = False

    for raw in categories:
        name = raw.split(":", 1)[-1]
        text = normalize_text(name)
        if not text:
            continue
        if AR_FEMININE.search(text):
            feminine = True
        for flag, pattern in AR_FLAGS.items():
            if pattern.search(text) and flag not in out["flags"]:
                out["flags"].append(flag)

        for field, patterns in AR_PATTERNS.items():
            matched = False
            for pattern in patterns:
                match = pattern.match(text)
                if not match:
                    continue
                matched = True
                if field in {"birth", "death"}:
                    if field not in out:
                        out[field] = f"{match.group(1)}-01-01"
                        out[f"{field}_precision"] = "year"
                else:
                    # Take the value from the ORIGINAL category name, not the
                    # folded one: folding is for matching only, and returning
                    # its output would store حركه النهضه instead of
                    # حركة النهضة. Folding never changes token counts, so the
                    # matched prefix can be measured in tokens and dropped.
                    prefix_tokens = len(text[:match.start(1)].split())
                    value = " ".join(name.split()[prefix_tokens:]).strip()
                    if not value:
                        break
                    if field == "birth_place":
                        out.setdefault("birth_place", value)
                    elif field == "education":
                        out["education_institutions"].append(value)
                    elif field == "party":
                        if not _AR_NOT_A_PARTY.match(normalize_text(value)):
                            out["parties"].append(value)
                break
            if matched:
                break

    if feminine:
        out["gender_hint"] = "female"
    for key in ("education_institutions", "parties", "awards", "employers",
                "memberships"):
        out[key] = _dedupe(out[key])
    return out


def _strip_article(value: str) -> str:
    return re.sub(r"^(du|de la|de l'|des|de|d'|au|à l'|à la|le|la|les|l')\s*", "",
                  value.strip(), flags=re.IGNORECASE).strip()


def _dedupe(values: list[str]) -> list[str]:
    seen, out = set(), []
    for value in values:
        key = normalize_text(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


# ---------------------------------------------------------------------------

def fetch_categories(
    titles: list[str], fetcher: Fetcher, lang: str = "fr"
) -> dict[str, dict[str, Any]]:
    """Categories and Wikidata id for a batch of articles."""
    result: dict[str, dict[str, Any]] = {}
    params = {
        "action": "query", "format": "json", "formatversion": "2",
        "titles": "|".join(titles),
        # pageprops carries the article's Wikidata item id. Resolving it here
        # costs nothing extra and is what lets a roster row inherit Wikidata's
        # structured attributes and a stable identifier - without it, anyone
        # who appears only in a cabinet table stays unidentified forever.
        "prop": "categories|pageprops", "ppprop": "wikibase_item",
        "cllimit": "max", "clshow": "!hidden", "redirects": "1",
    }
    while True:
        payload = fetcher.get_json(_api(lang), params)
        for page in payload.get("query", {}).get("pages", []):
            if page.get("missing"):
                continue
            entry = result.setdefault(page["title"], {"categories": [], "qid": None})
            entry["categories"].extend(
                c["title"] for c in page.get("categories", []) or []
            )
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if qid:
                entry["qid"] = qid
        cont = payload.get("continue")
        if not cont:
            break
        params = {**params, **cont}
    return result


def harvest(
    *, offline: bool = False, lang: str = "fr", limit: int | None = None
) -> list[dict[str, Any]]:
    """Harvest biographies for every officeholder linked from a cabinet roster."""
    fetcher = _fetcher(offline)
    interim = config.paths().ensure().interim

    cabinets = json.loads((interim / "wikipedia_cabinets.json").read_text(encoding="utf-8"))
    titles = sorted({
        member["person_wikilink"]
        for cabinet in cabinets
        if cabinet.get("lang") == lang
        for member in cabinet["members"]
        if member.get("person_wikilink")
    })
    if limit:
        titles = titles[:limit]
    log.info("[%s] %d biography articles to harvest", lang, len(titles))

    records: list[dict[str, Any]] = []
    for start in range(0, len(titles), BATCH):
        batch = titles[start:start + BATCH]
        try:
            categories = fetch_categories(batch, fetcher, lang)
        except Exception as exc:
            log.warning("category batch failed (%s...): %s", batch[0], exc)
            continue
        for title, entry in categories.items():
            record = parse_categories(entry["categories"], lang)
            record["qid"] = entry.get("qid")
            record["article"] = title
            record["lang"] = lang
            record["n_categories"] = len(entry["categories"])
            record["source_url"] = (
                f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
            )
            records.append(record)
        log.info("  %d/%d articles parsed", len(records), len(titles))

    path = interim / f"biographies_{lang}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=1, ensure_ascii=False)
    log.info("wrote %s (%d biographies)", path, len(records))
    fetcher.flush()
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--lang", default="fr")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    harvest(offline=args.offline, lang=args.lang, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
