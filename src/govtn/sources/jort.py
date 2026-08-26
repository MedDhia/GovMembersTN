"""Journal Officiel de la République Tunisienne (jort.tn).

The authoritative record: ministerial appointments take legal effect through a
decree published in the JORT, and the gazette is the only source here that can
date an appointment exactly rather than approximately. `docs/SOURCES.md`
previously told users to verify weighty claims against it by hand; this module
does that verification automatically and records the citation.

jort.tn indexes the gazette from 1957 to the present in French and Arabic -
the whole span of this dataset - with OCR'd full-text search.

WHAT THIS MODULE USES, AND WHAT IT DELIBERATELY DOES NOT
Full documents sit behind a login. This module uses only what the site serves
publicly: the search index, the result snippets, and each issue's own metadata
page, which carries the publication date and the summary of decrees. It never
requests the gated PDFs under lake.jort.tn, and never attempts to authenticate.
That is enough to produce a citation and a date for an appointment, which is
what the dataset needs.

The result is NOT a replacement for the harvested tenure dates. It is an
independent, authoritative citation attached alongside them, so a user can
check any given appointment against the gazette - and so disagreements between
the encyclopaedic sources and the official record become visible instead of
staying hidden.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from bs4 import BeautifulSoup

from .. import config
from ..http import Fetcher
from ..normalize import normalize_text, parse_date

log = logging.getLogger(__name__)

BASE = "https://jort.tn"

# Language of the decree that CREATES an office-holding, and of the one that
# ends it. Both are wanted: a cessation dates the end of a tenure as precisely
# as a nomination dates its start.
_NOMINATION = re.compile(
    r"est nomm[ée]|sont nomm[ée]s|nomination d|charg[ée] des fonctions|"
    r"est charg[ée] d|أسند|تسمية|يعين|عين .{0,20}وزير|كلف",
    re.IGNORECASE,
)
_CESSATION = re.compile(
    r"cessation de fonction|il est mis fin aux fonctions|mis fin aux fonctions|"
    r"إنهاء مهام|أعفي|اعفاء",
    re.IGNORECASE,
)
# Ministerial context, so a namesake in a list of promotions is not mistaken
# for a cabinet appointment.
_MINISTERIAL = re.compile(
    r"ministre|secr[ée]taire d'?[ÉEée]tat|chef du gouvernement|premier ministre|"
    r"وزير|كاتب دولة|رئيس الحكومة",
    re.IGNORECASE,
)

_NOT_CABINET = re.compile(
    r"ministre\s+pl[ée]nipotentiaire|conseiller\s+des\s+affaires\s+[ée]trang[èe]res|"
    r"fonctions\s+de\s+(?:premier\s+)?d[ée]l[ée]gu[ée]s?|d[ée]l[ée]gu[ée]s?\s+[àa]\s+compter|"
    r"وزير مفوض|معتمد",
    re.IGNORECASE,
)

_RESULT_META = re.compile(
    r"(?P<collection>Journal Officiel|Annonces L[ée]gales)\s*·\s*"
    r"(?P<year>\d{4})\s*/\s*N°(?P<issue>\d+)\s*·\s*page\s*(?P<page>\d+)\s*·\s*"
    r"(?P<lang>ar|fr)",
    re.IGNORECASE,
)

# "Jeudi 26 chaâbane 1442 – 8 avril 2021": the Gregorian half follows the dash.
# Taking the first number in the line would yield the Hijri year.
_ISSUE_DATE = re.compile(
    r"[–-]\s*(\d{1,2}\s+[a-zéûôàA-Z]+\s+(?:19|20)\d{2})"
)


@dataclass
class Hit:
    collection: str
    year: int
    issue: str
    page: int
    lang: str
    snippet: str
    url: str = ""
    is_nomination: bool = False
    is_cessation: bool = False
    is_ministerial: bool = False

    def as_citation(self) -> str:
        """A citation a reader can look up: JORT 2021, N°032, p. 3 (fr)."""
        return f"JORT {self.year}, N°{self.issue}, p. {self.page} ({self.lang})"


@dataclass
class JortClient:
    fetcher: Fetcher
    last_total: int | None = field(default=None, init=False)
    _issue_dates: dict[tuple, str | None] = field(default_factory=dict, init=False)

    def search(self, query: str, *, limit_pages: int = 1) -> list[Hit]:
        hits: list[Hit] = []
        for page in range(1, limit_pages + 1):
            params = {"q": query}
            if page > 1:
                params["page"] = page
            try:
                html = self.fetcher.get(f"{BASE}/", params)
            except Exception as exc:
                log.warning("jort search failed for %r: %s", query, exc)
                break
            if page == 1:
                self.last_total = self._parse_total(html)
            found = self._parse_results(html)
            if not found:
                break
            hits.extend(found)
        return hits

    @staticmethod
    def _parse_total(html: str) -> int | None:
        match = re.search(r"([\d\s\u202f\u00a0]+)\s*r[ée]sultats", html)
        if not match:
            text = re.sub(r"\s+", " ", BeautifulSoup(html, "lxml").get_text(" ", strip=True))
            match = re.search(r"([\d\s\u202f\u00a0]+)\s*r[ée]sultats", text)
        if not match:
            return None
        digits = re.sub(r"[^\d]", "", match.group(1))
        return int(digits) if digits else None

    @staticmethod
    def _parse_results(html: str) -> list[Hit]:
        soup = BeautifulSoup(html, "lxml")
        hits: list[Hit] = []
        for item in soup.find_all("li"):
            text = re.sub(r"\s+", " ", item.get_text(" ", strip=True))
            match = _RESULT_META.search(text)
            if not match:
                continue
            snippet = text[match.end():].strip(" ·")
            snippet = re.sub(r"🔒.*$", "", snippet).strip()
            hits.append(Hit(
                collection=match.group("collection"),
                year=int(match.group("year")),
                issue=match.group("issue"),
                page=int(match.group("page")),
                lang=match.group("lang").lower(),
                snippet=snippet[:400],
                is_nomination=bool(_NOMINATION.search(snippet)),
                is_cessation=bool(_CESSATION.search(snippet)),
                is_ministerial=bool(_MINISTERIAL.search(snippet)),
            ))
        return hits

    def issue_date(self, hit: Hit) -> str | None:
        """Publication date of the issue a hit sits in, as ISO.

        The issue page states it in both calendars; only the Gregorian half is
        taken. Cached, because many hits share an issue.
        """
        collection = ("journal-officiel" if "Journal" in hit.collection
                      else "annonces-legales")
        key = (collection, hit.lang, hit.year, hit.issue)
        if key in self._issue_dates:
            return self._issue_dates[key]

        url = f"{BASE}/view/{collection}/{hit.lang}/{hit.year}/{hit.issue}"
        value = None
        try:
            html = self.fetcher.get(url)
            text = re.sub(r"\s+", " ", BeautifulSoup(html, "lxml").get_text(" ", strip=True))
            match = _ISSUE_DATE.search(text)
            if match:
                parsed = parse_date(match.group(1))
                if parsed.value and parsed.value.year == hit.year:
                    value = parsed.value.isoformat()
        except Exception as exc:
            log.debug("issue date lookup failed for %s: %s", url, exc)
        self._issue_dates[key] = value
        return value


# ---------------------------------------------------------------------------
# Decree harvesting
# ---------------------------------------------------------------------------
# Searching per PERSON was the obvious approach and the wrong one: it surfaces
# every gazette mention of a name - a committee presidency, a board seat, a
# namesake in a promotion list - and cabinet appointments are a small minority
# of those. Searching for the APPOINTMENT LANGUAGE instead returns the actual
# appointment decrees, and the officeholder's name can be read off the
# snippet. It is also two orders of magnitude cheaper: a dozen queries rather
# than one per person.

DECREE_PHRASES: list[tuple[str, str]] = [
    # Head of government. The feminine form is a separate phrase, and omitting
    # it would lose both women who have held the office.
    ('"est nommé chef du gouvernement"', "head_of_government"),
    ('"est nommée cheffe du gouvernement"', "head_of_government"),
    ('"est nommée chef du gouvernement"', "head_of_government"),
    ('"est nommé Premier ministre"', "head_of_government"),
    ('"يعين رئيسا للحكومة"', "head_of_government"),
    # Whole-cabinet decrees.
    ('"sont nommés membres du gouvernement"', ""),
    ('"تسمية أعضاء الحكومة"', ""),
    ('"يسمى السيد"', ""),
    ('"يسمى السيدة"', ""),
    ('"عين السيد"', ""),
    ('"أسندت إلى السيد"', ""),
    ('"وزيرا لدى رئيس الحكومة"', ""),
    # Individual ministers and secretaries of state.
    ('"est nommé ministre"', ""),
    ('"est nommée ministre"', ""),
    ('"est nommé secrétaire d\'Etat"', ""),
    ('"est nommée secrétaire d\'Etat"', ""),
    # Cessations date the END of a tenure as precisely as a nomination dates
    # its start.
    # Targeted at ministers: the unqualified forms return mostly délégués and
    # other sub-national posts.
    ('"il est mis fin aux fonctions de ministre"', ""),
    ('"cessation de fonctions du ministre"', ""),
    ('"cessation de fonctions de membres du gouvernement"', ""),
    ('"إنهاء مهام عضو بالحكومة"', ""),
]

# "Article premier - Monsieur Ahmed Hachani est nommé Chef du Gouvernement"
#
# The honorific is allowed to be TRUNCATED. Snippets are cut to a fixed width
# and frequently begin mid-word - "...sieur Mohamed MZALI est nommé Premier
# Ministre" - so requiring the whole of "Monsieur" discarded a large share of
# otherwise perfect matches.
_HOLDER = re.compile(
    # "sieur" and "dame" on their own are the tails of Monsieur/Madame left by
    # the snippet's fixed-width cut.
    r"(?:(?:M(?:on)?)?sieur|(?:Ma)?dame|M\.|Mme)\s+"
    r"(?P<name>[^,;]{3,70}?)\s*,?\s*"
    r"(?:est\s+nomm|sont\s+nomm|,)",
    re.IGNORECASE,
)

# A decree's preamble cites the decrees it relies on: "وعلى الأمر عدد ... المتعلق
# بتسمية أعضاء الحكومة" - "having regard to decree no. X concerning the naming
# of members of the government". Those are references TO an appointment
# decree, not appointment decrees, and they were the single largest group of
# unparseable results.
_PREAMBLE_REFERENCE = re.compile(
    r"وعلى الأمر|وعلى المرسوم|المتعلق ب|بمقتضى الأمر|"
    r"vu le d[ée]cret|vu la loi",
    re.IGNORECASE,
)
# Titles and ranks that precede the office but are not part of the name.
_NAME_NOISE = re.compile(
    r"\b(conseiller|ministre|secr[ée]taire|directeur|pr[ée]sident|g[ée]n[ée]ral|"
    r"professeur|docteur|ma[iî]tre|ambassadeur)\b.*$",
    re.IGNORECASE,
)


# The office named after the appointment verb: "est nommé ministre de
# l'intérieur", "est nommée cheffe du gouvernement".
_OFFICE_AFTER_VERB = re.compile(
    r"(?:est|sont)\s+nomm[ées]{1,3}\s+(?P<office>[^.,;]{4,80})",
    re.IGNORECASE,
)


# "à compter du 25 août 2014" - the date the decree TAKES EFFECT, which is the
# appointment's actual legal date. It beats the publication date, which merely
# trails it, and it is stated in the snippet often enough to be worth taking.
_EFFECTIVE_DATE = re.compile(
    r"[àa]\s+compter\s+du\s+(?P<date>\d{1,2}\s+[a-zéûôàA-Z]+\s+(?:19|20)\d{2})",
    re.IGNORECASE,
)


def extract_effective_date(snippet: str) -> str | None:
    """The decree's effective date, as ISO, or None."""
    match = _EFFECTIVE_DATE.search(snippet)
    if not match:
        return None
    parsed = parse_date(match.group("date"))
    return parsed.value.isoformat() if parsed.value else None


def extract_office(snippet: str) -> str | None:
    """The office a decree appoints to, as printed."""
    match = _OFFICE_AFTER_VERB.search(snippet)
    if not match:
        return None
    office = re.sub(r"\s+", " ", match.group("office")).strip(" .,;-")
    return office or None


def extract_holder(snippet: str) -> str | None:
    """Officeholder's name from a decree snippet, or None."""
    match = _HOLDER.search(snippet)
    if not match:
        return None
    name = _NAME_NOISE.sub("", match.group("name")).strip(" ,.;-")
    name = re.sub(r"\s+", " ", name)
    # Two to six tokens. Tunisian names carry particles ("Zine El Abidine Ben
    # Ali" is five), and an upper bound of four rejected exactly the
    # multi-particle names that matter most here.
    if not 2 <= len(name.split()) <= 6:
        return None
    return name


def harvest_decrees(
    client: JortClient, *, phrases: list[tuple[str, str]] | None = None,
    max_pages: int = 10,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Appointment and cessation decrees, with citation, date and holder.

    Returns (decrees, truncated) where `truncated` records any query whose
    result set exceeded the page cap, so a partial sweep is never mistaken for
    a complete one.
    """
    decrees: list[dict[str, Any]] = []
    truncated: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    skipped_preamble = 0
    skipped_non_ministerial = 0
    for query, portfolio_hint in phrases or DECREE_PHRASES:
        hits = client.search(query, limit_pages=max_pages)
        total = client.last_total
        # Never let a cap look like exhaustive coverage.
        if total and total > len(hits):
            log.info("%-44s %4d fetched of %d total (capped at %d pages)",
                     query, len(hits), total, max_pages)
            truncated.append({"query": query, "fetched": len(hits), "total": total})
        else:
            log.info("%-44s %4d hits", query, len(hits))
        for hit in hits:
            key = (hit.year, hit.issue, hit.page, hit.lang, hit.snippet[:60])
            if key in seen:
                continue
            seen.add(key)
            if not hit.collection.startswith("Journal"):
                continue                     # Annonces Légales are company filings
            if _PREAMBLE_REFERENCE.search(hit.snippet) and not _HOLDER.search(hit.snippet):
                # A preamble citing an appointment decree, not the decree.
                skipped_preamble += 1
                continue
            if hit.is_cessation and not hit.is_ministerial and not portfolio_hint:
                # Generic cessation results are dominated by sub-national
                # administrative posts; without ministerial context they are
                # not this dataset's business.
                skipped_non_ministerial += 1
                continue
            if _NOT_CABINET.search(hit.snippet):
                # "Ministre plénipotentiaire" is a diplomatic rank, not a seat
                # in the cabinet, and it dominates these results.
                continue
            decrees.append({
                "citation": hit.as_citation(),
                "year": hit.year,
                "issue": hit.issue,
                "page": hit.page,
                "lang": hit.lang,
                "kind": "cessation" if hit.is_cessation else "nomination",
                "portfolio_hint": portfolio_hint or None,
                "holder": extract_holder(hit.snippet),
                "office": extract_office(hit.snippet),
                "effective": extract_effective_date(hit.snippet),
                "published": client.issue_date(hit),
                "snippet": hit.snippet,
                "query": query,
                "url": f"{BASE}/view/journal-officiel/{hit.lang}/{hit.year}/{hit.issue}",
            })
    if skipped_preamble:
        log.info("skipped %d preamble references to appointment decrees",
                 skipped_preamble)
    if skipped_non_ministerial:
        log.info("skipped %d cessations with no ministerial context",
                 skipped_non_ministerial)
    return decrees, truncated


def harvest(*, offline: bool = False, max_pages: int = 10) -> list[dict[str, Any]]:
    fetcher = Fetcher(source="jort", rate_limit=2.5, timeout=45, offline=offline)
    client = JortClient(fetcher)
    interim = config.paths().ensure().interim

    decrees, truncated = harvest_decrees(client, max_pages=max_pages)
    named = [d for d in decrees if d["holder"]]
    dated = [d for d in decrees if d["published"]]
    log.info(
        "%d decrees; %d with an identifiable holder, %d with a publication date",
        len(decrees), len(named), len(dated),
    )

    if truncated:
        log.warning(
            "%d queries exceeded the page cap; coverage is partial: %s",
            len(truncated),
            ", ".join(f"{t['query']} ({t['fetched']}/{t['total']})" for t in truncated),
        )
    path = interim / "jort_decrees.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump({"decrees": decrees, "truncated": truncated}, fh,
                  indent=1, ensure_ascii=False)
    log.info("wrote %s", path)
    fetcher.flush()
    return decrees


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    harvest(offline=args.offline, max_pages=args.max_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
