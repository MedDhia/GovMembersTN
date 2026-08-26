"""Leaders.com.tn biography harvester.

Leaders is a Tunisian outlet that runs a long-standing "Who's Who" section and
a directory of public figures. It matters here because it fills the single
biggest gap in the structured sources: EDUCATION AND PRE-MINISTERIAL CAREER.
Wikidata records that a person was interior minister; Leaders records that he
was a Kasserine magistrate first, which is the kind of variable elite-politics
work actually needs (technocrat vs. party cadre vs. security professional).

Copyright note: this harvester deliberately does not retain article bodies.
It stores the extracted structured fields, plus a short excerpt around each
extraction so a human can verify the value, plus the source URL. That is
enough to audit the dataset without redistributing the outlet's text; the
behaviour is controlled by `store_full_text` in config/sources.yml.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import config
from ..http import Fetcher
from ..normalize import normalize_text, parse_date

log = logging.getLogger(__name__)


def _fetcher(offline: bool = False) -> Fetcher:
    cfg = config.sources()["leaders"]
    return Fetcher(
        source="leaders",
        rate_limit=cfg["rate_limit_seconds"],
        timeout=cfg["timeout_seconds"],
        offline=offline,
    )


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------
# French biographical prose is formulaic enough for pattern extraction, but
# the patterns must tolerate the variants that actually occur:
#   "Né le 15 août 1955 à Médenine"
#   "née à Kairouan le 6 juin 1958"
#   "Naissance : 31 juillet 1964 à Sbeitla"

_BIRTH_PATTERNS = [
    re.compile(r"n[ée]+\(?e?\)?\s+le\s+(?P<date>\d{1,2}\s+\w+\s+\d{4})"
               r"(?:\s+[àa]\s+(?P<place>[^.,;()]{2,40}))?", re.IGNORECASE),
    re.compile(r"n[ée]+\(?e?\)?\s+[àa]\s+(?P<place>[^.,;()]{2,40})\s*,?\s*"
               r"le\s+(?P<date>\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE),
    re.compile(r"naissance\s*:\s*(?P<date>\d{1,2}\s+\w+\s+\d{4})"
               r"(?:\s+[àa]\s+(?P<place>[^.,;()]{2,40}))?", re.IGNORECASE),
    re.compile(r"n[ée]+\(?e?\)?\s+en\s+(?P<date>\d{4})"
               r"(?:\s+[àa]\s+(?P<place>[^.,;()]{2,40}))?", re.IGNORECASE),
]

# Education. Institution and degree are captured SEPARATELY because they are
# different variables: which grande école someone attended is a network tie,
# what diploma they hold is a credential level. Naive patterns conflate them -
# "diplômé de l'ENA" (institution) and "diplôme d'ingénieur" (degree) differ
# only by an accent, so the participle is matched accent-sensitively.

# Ordered longest-first; "de l'" must be tried before "de ", and "du " must be
# its own branch, or the article is left glued to the institution name
# ("du Lycée" -> "ycée").
_ARTICLE = r"(?:de\s+l['’]|de\s+la\s+|des\s+|du\s+|de\s+|d['’])"

_DEGREE_WORDS = (
    r"doctorat|habilitation|agr[ée]gation|ma[iî]trise|master[e]?|mba|licence|"
    r"dea|dess|dipl[oô]me\s+d['’]ing[ée]nieur|dipl[oô]me|baccalaur[ée]at"
)

_EDUCATION_PATTERNS = [
    # "diplômé de l'École polytechnique" - participle, so institution follows.
    re.compile(rf"dipl[oô]m(?:é|ée|és|ées)\s+{_ARTICLE}\s*(?P<inst>[^.,;()]{{4,80}})",
               re.IGNORECASE),
    re.compile(rf"(?:ancien(?:ne)?s?\s+[ée]l[èe]ve|laur[ée]at[e]?)\s+{_ARTICLE}\s*"
               rf"(?P<inst>[^.,;()]{{4,80}})", re.IGNORECASE),
    re.compile(rf"(?:[ée]tudes|formation|scolarit[ée])\s+(?:à|au|aux|à\s+l['’])\s*"
               rf"(?P<inst>[^.,;()]{{4,80}})", re.IGNORECASE),
]

# "titulaire d'une maîtrise en droit de la Faculté des sciences juridiques"
# -> degree=maîtrise, field=droit, institution=Faculté des sciences juridiques
_DEGREE_PATTERNS = [
    re.compile(rf"(?:titulaire|dot[ée]e?)\s+d['’]un[e]?\s+(?P<degree>{_DEGREE_WORDS})"
               rf"(?:\s+(?:en|de|d['’])\s*(?P<field>[^.,;()]{{3,40}}?))?"
               rf"(?:\s+{_ARTICLE}\s*(?P<inst>[^.,;()]{{4,70}}))?(?=[.,;()]|$)",
               re.IGNORECASE),
    re.compile(rf"(?P<degree>{_DEGREE_WORDS})\s+(?:en|d['’])\s*(?P<field>[^.,;()]{{3,40}})",
               re.IGNORECASE),
]

# Occupation before entering government. Terms that are ambiguous on their own
# are required to appear with a disambiguating qualifier: a merchant-marine
# "officier" is not a security professional, and coding him as one would
# corrupt exactly the technocrat/security distinction this variable exists for.
_PROFESSION_PATTERNS = {
    "law": r"avocat|magistrat|juge\b|juriste|notaire|conseiller\s+juridique",
    "engineering": r"ing[ée]nieur|polytechnicien|architecte",
    "medicine": r"m[ée]decin|chirurgien|pharmacien|professeur\s+de\s+m[ée]decine",
    "academia": r"universitaire|professeur\s+(?:à|des\s+universit|d['’]universit)|"
                r"enseignant[- ]chercheur|chercheur\b|doyen\b|recteur\b",
    "economics": r"[ée]conomiste",
    "finance": r"banquier|expert[- ]comptable|financier\b|gouverneur\s+de\s+la\s+banque",
    "diplomacy": r"diplomate|ambassadeur|consul\b",
    "security": r"officier\s+(?:de\s+police|de\s+l['’]arm[ée]e|sup[ée]rieur)|"
                r"g[ée]n[ée]ral\b|colonel\b|commissaire\s+de\s+police|"
                r"directeur\s+de\s+la\s+s[ée]curit[ée]",
    "media": r"journaliste|r[ée]dacteur\s+en\s+chef",
    "labour": r"syndicaliste|secr[ée]taire\s+g[ée]n[ée]ral\s+de\s+l['’]ugtt",
    "business": r"homme\s+d['’]affaires|chef\s+d['’]entreprise|patron\s+de",
    "civil_service": r"haut\s+fonctionnaire|administrateur\s+g[ée]n[ée]ral|"
                     r"secr[ée]taire\s+g[ée]n[ée]ral\s+du\s+minist",
}
_PROFESSION_COMPILED = {
    domain: re.compile(pattern, re.IGNORECASE)
    for domain, pattern in _PROFESSION_PATTERNS.items()
}


def _excerpt(text: str, match: re.Match, width: int) -> str:
    start = max(0, match.start() - width // 2)
    return re.sub(r"\s+", " ", text[start:start + width]).strip()


def parse_biography(html: str, url: str, *, excerpt_chars: int = 400) -> dict[str, Any]:
    """Extract structured biographical fields from a Leaders article.

    Every extracted value is returned with the excerpt it came from, so a
    coder can verify it against the source without re-fetching the page.
    """
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()

    heading = soup.find(["h1", "h2"])
    title = heading.get_text(" ", strip=True) if heading else ""

    body_node = (
        soup.find("article")
        or soup.find(class_=re.compile(r"article|content|body|texte", re.I))
        or soup.body
        or soup
    )
    text = re.sub(r"\s+", " ", body_node.get_text(" ", strip=True))

    record: dict[str, Any] = {
        "source_url": url,
        "article_title": title,
        "evidence": {},
    }

    # -- birth -------------------------------------------------------------
    for pattern in _BIRTH_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groupdict()
        parsed = parse_date(groups.get("date"))
        if parsed.value:
            record["birth_date"] = parsed.value.isoformat()
            record["birth_date_precision"] = parsed.precision
        place = (groups.get("place") or "").strip()
        if place:
            record["birth_place"] = place
        record["evidence"]["birth"] = _excerpt(text, match, excerpt_chars)
        break

    # -- education ---------------------------------------------------------
    institutions: list[str] = []
    for pattern in _EDUCATION_PATTERNS:
        for match in pattern.finditer(text):
            inst = (match.group("inst") or "").strip(" '’\t")
            if inst and 4 <= len(inst) <= 80:
                institutions.append(inst)
                record["evidence"].setdefault("education", _excerpt(text, match, excerpt_chars))
    if institutions:
        record["education_institutions"] = _dedupe(institutions)

    # -- degrees -----------------------------------------------------------
    degrees: list[dict[str, str]] = []
    for pattern in _DEGREE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            entry = {
                key: value.strip(" '’\t")
                for key, value in groups.items() if value and value.strip()
            }
            if entry.get("degree"):
                degrees.append(entry)
                record["evidence"].setdefault("degree", _excerpt(text, match, excerpt_chars))
                # An institution named alongside a degree is still an institution.
                if entry.get("inst"):
                    institutions.append(entry["inst"])
    if degrees:
        seen, unique = set(), []
        for entry in degrees:
            key = normalize_text(entry.get("degree", ""))
            if key not in seen:
                seen.add(key)
                unique.append(entry)
        record["degrees"] = unique
    if institutions:
        record["education_institutions"] = _dedupe(institutions)

    # -- profession --------------------------------------------------------
    professions = sorted(
        domain for domain, pattern in _PROFESSION_COMPILED.items()
        if pattern.search(text)
    )
    if professions:
        record["profession_domains"] = professions

    return record


def _dedupe(values: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for value in values:
        key = normalize_text(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value.strip())
    return out


# ---------------------------------------------------------------------------
# Crawling
# ---------------------------------------------------------------------------

_ARTICLE_HREF = re.compile(r"/(article|annuaire-personnalite)/")


def list_section_articles(
    section: str, fetcher: Fetcher, *, max_pages: int = 40
) -> list[str]:
    """Article URLs in a Leaders section, following pagination."""
    base = config.sources()["leaders"]["base_url"]
    urls: list[str] = []
    for page in range(1, max_pages + 1):
        url = urljoin(base, section.lstrip("/"))
        params = {"page": page} if page > 1 else None
        try:
            html = fetcher.get(url, params)
        except Exception as exc:
            log.warning("listing %s page %d failed: %s", section, page, exc)
            break
        soup = BeautifulSoup(html, "lxml")
        found = [
            urljoin(base, a["href"])
            for a in soup.find_all("a", href=True)
            if _ARTICLE_HREF.search(a["href"])
        ]
        new = [u for u in found if u not in urls]
        if not new:
            break                                     # pagination exhausted
        urls.extend(new)
        log.info("%s page %d: +%d (%d total)", section, page, len(new), len(urls))
    return urls


def harvest(*, offline: bool = False, max_pages: int = 40) -> list[dict[str, Any]]:
    """Crawl the biographical sections and extract structured fields."""
    cfg = config.sources()["leaders"]
    fetcher = _fetcher(offline)
    interim = config.paths().ensure().interim

    urls: list[str] = []
    for section in cfg["sections"]:
        urls.extend(list_section_articles(section["path"], fetcher, max_pages=max_pages))
    urls = _dedupe(urls)
    log.info("%d Leaders biography URLs", len(urls))

    records: list[dict[str, Any]] = []
    for url in urls:
        try:
            html = fetcher.get(url)
        except Exception as exc:
            log.warning("fetch failed for %s: %s", url, exc)
            continue
        record = parse_biography(html, url, excerpt_chars=cfg["excerpt_chars"])
        # Keep only rows that yielded at least one usable field.
        if any(k in record for k in
               ("birth_date", "birth_place", "education_institutions", "profession_domains")):
            records.append(record)

    path = interim / "leaders_biographies.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=1, ensure_ascii=False)
    log.info("wrote %s (%d biographies with extracted fields)", path, len(records))
    fetcher.flush()
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--max-pages", type=int, default=40)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    harvest(offline=args.offline, max_pages=args.max_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
