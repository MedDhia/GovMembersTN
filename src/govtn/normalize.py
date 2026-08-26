"""Normalisation of names, ministerial titles and dates.

Three problems this module solves, all of which silently corrupt Tunisian
elite datasets if ignored:

1. TRANSLITERATION VARIANCE. The same person appears as "Béji Caïd Essebsi",
   "Beji Caid Essebsi", "El Béji Caïd Es-Sebsi" and "الباجي قائد السبسي".
   French-language Tunisian sources use a French-derived romanisation
   (ou = /u/, ch = /ʃ/, dj = /dʒ/) while English sources use an
   English-derived one (u, sh, j). Naive string matching splits one person
   into four.

2. TITLE INSTABILITY. Ministries are renamed and merged constantly, and the
   cabinet RANK (minister / secretary of state / delegate minister) is fused
   into the same string as the policy DOMAIN. Both must be parsed out.

3. DATE FORMATS. Tunisian Arabic uses French-derived month names
   (جانفي, فيفري, أفريل, جوان, جويلية, أوت) rather than the Levantine ones
   (يناير, فبراير...). A parser built for Modern Standard Arabic silently
   fails on roughly half of Tunisian sources.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from datetime import date
from typing import Iterable, NamedTuple

from . import config

# ---------------------------------------------------------------------------
# Script-level normalisation
# ---------------------------------------------------------------------------

_ARABIC_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")

_ARABIC_FOLD = {
    "آ": "ا",  # آ -> ا
    "أ": "ا",  # أ -> ا
    "إ": "ا",  # إ -> ا
    "ٱ": "ا",  # ٱ -> ا
    "ة": "ه",  # ة -> ه
    "ى": "ي",  # ى -> ي
    "ؤ": "و",  # ؤ -> و
    "ئ": "ي",  # ئ -> ي
}

_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def strip_latin_diacritics(text: str) -> str:
    """é -> e, ï -> i, ç -> c. Leaves non-Latin scripts untouched."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def normalize_arabic(text: str) -> str:
    """Fold Arabic orthographic variants and strip vocalisation."""
    text = unicodedata.normalize("NFC", text)
    text = _ARABIC_DIACRITICS.sub("", text)
    for src, dst in _ARABIC_FOLD.items():
        text = text.replace(src, dst)
    return text.translate(_ARABIC_INDIC_DIGITS)


def has_arabic(text: str) -> bool:
    return any("؀" <= c <= "ۿ" for c in text)


def normalize_text(text: str) -> str:
    """Lowercase, de-accent, fold Arabic, squash whitespace."""
    if text is None:
        return ""
    text = normalize_arabic(str(text))
    text = strip_latin_diacritics(text).lower()
    text = text.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    text = re.sub(r"[‐-―]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Person names
# ---------------------------------------------------------------------------

# Nobiliary / patronymic particles that appear inconsistently and must not
# drive a match decision. "Ben" is kept - it is a meaningful name element in
# Tunisia (Ben Ali, Ben Salah) - but normalised to one spelling.
_PARTICLE_FOLD = [
    (r"\bbin\b", "ben"),
    (r"\bibn\b", "ben"),
    (r"\bb\.\s*", "ben "),
    (r"\bes[- ]", "el "),
    (r"\bas[- ]", "el "),
    (r"\bal[- ]", "el "),
    (r"\bel[- ]", "el "),
    (r"\bech[- ]", "el "),
    (r"\bez[- ]", "el "),
    (r"\ber[- ]", "el "),
    (r"\bet[- ]", "el "),
    (r"\babd\s+el\s+", "abdel"),
    (r"\babd\s+al\s+", "abdel"),
    (r"\babdul\b", "abdel"),
    (r"\babdoul\b", "abdel"),
]

# French-romanisation -> neutral skeleton. Order matters: multi-character
# digraphs must be folded before their constituent letters.
_TRANSLIT_FOLD = [
    (r"tch", "c"),
    (r"dj", "j"),
    (r"ch", "c"),   # French /ʃ/
    (r"sh", "c"),   # English /ʃ/
    (r"kh", "x"),
    (r"gh", "q"),
    (r"th", "t"),
    (r"dh", "d"),
    (r"ph", "f"),
    (r"ou", "u"),   # French /u/
    (r"oo", "u"),
    (r"aa", "a"),
    (r"ee", "i"),
    (r"ii", "i"),
    (r"ss", "s"),
    (r"ll", "l"),
    (r"mm", "m"),
    (r"nn", "n"),
    (r"tt", "t"),
    (r"rr", "r"),
    (r"dd", "d"),
    (r"bb", "b"),
    (r"ff", "f"),
    (r"y", "i"),
    (r"w", "u"),
    (r"k", "q"),    # Kais / Qais
    (r"e", "a"),    # short-vowel transliteration is unstable across sources
    (r"o", "u"),
]


def clean_name(name: str) -> str:
    """Human-readable normalised form: keeps spacing and word order."""
    text = normalize_text(name)
    text = re.sub(r"\([^)]*\)", " ", text)          # drop parenthetical glosses
    text = re.sub(r"[^\w\s'؀-ۿ-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Arabic definite-article prefixes as they surface in French/English
# romanisation of Tunisian names, including sun-letter assimilation:
#   الشيخ  -> "Escheikh" / "Ech-Cheikh" / "Cheikh"
#   السبسي -> "Essebsi" / "Es-Sebsi" / "Sebsi"
# Longest first, so "ech" is tried before "e".
_ARTICLE_PREFIXES = ("ech", "ash", "esh", "el", "al", "es", "as", "ez",
                     "er", "et", "ed", "en", "ac", "ad")


def _strip_article_prefix(token: str) -> str:
    """Remove a fused Arabic definite article from the head of a token.

    Only applied when at least three characters survive, which protects short
    genuine names ("Ali" must not become "i", "Adel" must not become "el").
    """
    for prefix in _ARTICLE_PREFIXES:
        if token.startswith(prefix) and len(token) - len(prefix) >= 3:
            rest = token[len(prefix):]
            if rest[0] not in "aeiou":          # article attaches to a consonant
                return rest
    return token


def name_key(name: str) -> str:
    """Moderate-strength blocking key.

    Folds particles and the main French/English romanisation differences but
    keeps vowel structure. Suitable as the primary join key.
    """
    text = clean_name(name)
    for pattern, repl in _PARTICLE_FOLD:
        text = re.sub(pattern, repl, text)
    text = text.replace("'", "").replace("-", " ")
    # "Abdelhamid" and "Abdel Hamid" are the same name tokenised differently.
    text = re.sub(r"\babdel(?=[a-z]{3,})", "abdel ", text)
    return re.sub(r"\s+", " ", text).strip()


def name_tokens_strong(name: str) -> frozenset[str]:
    """Aggressive romanisation-invariant token set for candidate generation.

    Collapses the French/English transliteration split (ou/u, ch/sh, dj/j,
    k/q), fused definite articles, doubled consonants and unstable final
    vowels, so that these all yield the same token set:

        "Béji Caïd Essebsi" / "Beji Caid Essebsi" / "El Béji Caïd Es-Sebsi"
        "Zine El Abidine Ben Ali" / "Zin al-Abidin Bin Ali"

    It over-collapses by design and must never be used as the sole basis for
    a merge; `reconcile` scores candidates it generates before accepting them.
    Returned as a SET, not a string, so that names differing only by the
    presence of a middle name ("Hédi Nouira" vs "Hédi Amara Nouira") can be
    compared by overlap rather than equality.
    """
    text = name_key(name)
    if has_arabic(text):
        return frozenset(t for t in text.split() if len(t) > 1)

    tokens: list[str] = []
    for token in text.split():
        token = _strip_article_prefix(token)
        for pattern, repl in _TRANSLIT_FOLD:
            token = re.sub(pattern, repl, token)
        token = re.sub(r"(.)\1+", r"\1", token)      # collapse doubles
        if len(token) > 3:
            token = re.sub(r"a$", "", token)          # unstable final vowel
        # Bare definite articles carry no identifying information.
        if token in {"al", "a", "l"} or len(token) < 2:
            continue
        tokens.append(token)
    return frozenset(tokens)


def name_key_strong(name: str) -> str:
    """String form of :func:`name_tokens_strong`, for use as a dict key."""
    return " ".join(sorted(name_tokens_strong(name)))


def name_similarity(a: str, b: str) -> float:
    """Similarity in [0, 1] between two person names.

    Jaccard overlap of the strong token sets, with a containment override:
    when one name's tokens are a strict subset of the other's, the pair is
    scored 0.9 rather than penalised. That case is systematic in this data -
    sources drop middle names inconsistently ("Hédi Nouira" in a cabinet
    table, "Hédi Amara Nouira" in the biography) - and plain Jaccard would
    push those genuine matches below any usable threshold.
    """
    ta, tb = name_tokens_strong(a), name_tokens_strong(b)
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    intersection = len(ta & tb)
    if not intersection:
        return 0.0
    if ta <= tb or tb <= ta:
        return 0.9
    return intersection / len(ta | tb)


# ---------------------------------------------------------------------------
# Ministerial titles
# ---------------------------------------------------------------------------

class ParsedTitle(NamedTuple):
    raw: str
    rank: str
    portfolio: str
    is_interim: bool
    is_acting: bool
    matched_alias: str | None


_INTERIM = re.compile(r"\b(interim|par interim|interimaire|بالنيابة|بالانابة)\b")
_ACTING = re.compile(r"\b(charge de l'?expedition|acting|faisant fonction|مكلفب?تسيير)\b")


def normalize_title(title: str) -> str:
    """Normalised form used for portfolio/rank regex matching."""
    text = normalize_text(title)
    text = re.sub(r"\[\[|\]\]", " ", text)          # stray wiki markup
    # Parenthetical glosses annotate the holder, not the office
    # ("ministre d'État (destourien)"), and block exact rank matching.
    text = re.sub(r"\([^)]*\)", " ", text)
    # French articles are deliberately KEPT. Rank patterns are anchored phrases
    # ("chef du gouvernement", "ministre delegue") and stripping "du"/"de la"
    # out from under them makes every anchored rank alias fail to match.
    text = re.sub(r"[^\w\s'؀-ۿ-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@functools.lru_cache(maxsize=1)
def _compiled_taxonomy() -> tuple[list, list, str]:
    cfg = config.portfolios()
    # Alias patterns are written in the config in natural orthography
    # ("الداخلية", "secrétaire d'État"). The strings they are matched against
    # have been through `normalize_title`, which folds Arabic orthography
    # (ة -> ه, أ -> ا) and strips Latin diacritics. The patterns must undergo
    # the same folding or they can never match. `normalize_arabic` and
    # `strip_latin_diacritics` touch no regex metacharacter, so this is safe.
    def _compile(alias: str) -> re.Pattern:
        return re.compile(strip_latin_diacritics(normalize_arabic(alias)).lower())

    ranks = [
        (item["canonical"], item.get("level", 99),
         [_compile(a) for a in item.get("aliases", [])])
        for item in cfg["ranks"]
    ]
    portfolios = [
        (item["canonical"], [_compile(a) for a in item.get("aliases", [])])
        for item in cfg["portfolios"]
    ]
    return ranks, portfolios, cfg["unmatched"]["canonical"]


@functools.lru_cache(maxsize=1)
def _compiled_exclusions() -> list[tuple[str, list]]:
    cfg = config.portfolios()
    return [
        (block["id"],
         [re.compile(strip_latin_diacritics(normalize_arabic(p)).lower())
          for p in block["patterns"]])
        for block in cfg.get("exclude", [])
    ]


def excluded_reason(raw: str) -> str | None:
    """Why this title is not membership of a government, or None if it is.

    Wikidata's "Tunisian government positions" include parliamentarians,
    foreign ambassadors to Tunis, religious offices and mayors. They are not
    members of a government and must not sit in the appointments table.
    """
    text = normalize_title(raw)
    if not text:
        return None
    for block_id, patterns in _compiled_exclusions():
        if any(p.search(text) for p in patterns):
            return block_id
    return None


# An institution or an office title, not a person. These reach the person
# column when a roster row is misaligned or records a vacant post by naming
# the ministry. Left in, they become "people" with careers and network ties.
_OFFICE_AS_NAME = re.compile(
    r"^(le |la |l')?("
    r"minist(ere|re|ère)|secretariat|secretaire d'?etat|presidence|premier ministere|"
    r"chef du gouvernement|gouvernement|direction|departement|agence|"
    r"conseil|assemblee|republique|banque centrale|office\b|"
    r"وزار[ةه]|رئاس[ةه]|كتاب[ةه]|الحكوم[ةه]|مجلس"
    r")\b"
)


def looks_like_office(name: str) -> bool:
    """True when a supposed person name is really an institution or a post."""
    return bool(_OFFICE_AS_NAME.match(normalize_text(name)))


def parse_title(raw: str) -> ParsedTitle:
    """Split a raw ministerial title into cabinet rank and policy portfolio.

    Matching is ordered: the first declared alias that matches wins, which is
    why `config/portfolios.yml` declares specific portfolios before general
    ones. Unmatched titles get the `other` portfolio and are reported by
    `govtn.validate` so the taxonomy can be extended.
    """
    text = normalize_title(raw)
    ranks, portfolios, fallback = _compiled_taxonomy()

    rank = "minister"        # the modal rank; overridden below when signalled
    for canonical, _level, patterns in ranks:
        if any(p.search(text) for p in patterns):
            rank = canonical
            break

    portfolio, matched = fallback, None
    for canonical, patterns in portfolios:
        for pattern in patterns:
            if pattern.search(text):
                portfolio, matched = canonical, pattern.pattern
                break
        if matched:
            break

    # A rank-only title ("Ministre d'État", "Ministre sans portefeuille") names
    # no policy domain. Coding it as `other` would pool it with genuinely
    # unclassified portfolios and pollute the taxonomy-coverage diagnostics.
    if portfolio == fallback and rank in {
        "minister_of_state", "minister", "secretary_of_state"
    }:
        if re.fullmatch(
            r"ministre d'?etat|minister of state|وزير دوله|كاتب دوله|"
            r"secretaire d'?etat|ministre sans portefeuille", text
        ):
            portfolio = "without_portfolio"

    return ParsedTitle(
        raw=raw,
        rank=rank,
        portfolio=portfolio,
        is_interim=bool(_INTERIM.search(text)),
        is_acting=bool(_ACTING.search(text)),
        matched_alias=matched,
    )


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_FR_MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}

# Tunisian Arabic uses French-derived month names, unlike Levantine Arabic.
# Both sets are accepted; getting this wrong loses ~half of Arabic sources.
_AR_MONTHS = {
    "جانفي": 1, "فيفري": 2, "مارس": 3, "افريل": 4, "ماي": 5, "جوان": 6,
    "جويلية": 7, "اوت": 8, "سبتمبر": 9, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
    # Levantine / MSA forms, for pan-Arab sources
    "يناير": 1, "فبراير": 2, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7,
    "اغسطس": 8, "اب": 8, "ايلول": 9, "تشرين الاول": 10, "تشرين الثاني": 11,
    "كانون الاول": 12, "كانون الثاني": 1, "شباط": 2, "اذار": 3, "نيسان": 4,
    "ايار": 5, "حزيران": 6, "تموز": 7,
}

_EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

# Month names are looked up in text that has already been through
# `normalize_text`, which folds Arabic orthography (ة -> ه, أ -> ا). The keys
# must be folded identically or e.g. "جويلية" (July) never matches its own
# entry and silently degrades to year precision.
_ALL_MONTHS = {
    normalize_arabic(name): number
    for name, number in {**_FR_MONTHS, **_EN_MONTHS, **_AR_MONTHS}.items()
}

# The trailing boundary is a negative lookahead, not `\b`. Wikidata returns
# timestamps as "1903-08-03T00:00:00Z", and `\b` does not match between the
# final digit and the "T" - so the date failed here, fell through to the
# year-only branch, and every Wikidata date silently became 1 January of its
# year. That degraded 1304 of 1354 harvested tenure dates before it was caught.
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?![\d-])")
_DMY_NUM = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")
_YEAR_MONTH = re.compile(r"\b(1[89]\d{2}|20\d{2})-(0[1-9]|1[0-2])\b")
_YEAR_ONLY = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


class ParsedDate(NamedTuple):
    value: date | None
    precision: str       # "day" | "month" | "year" | "unknown"
    raw: str


def parse_date(raw: str | None) -> ParsedDate:
    """Parse a date in French, Arabic, English or ISO form.

    Returns the parsed value together with its PRECISION. Precision is not
    cosmetic: a tenure bounded by year-precision endpoints cannot support a
    duration-in-days measure, and `build` propagates this flag so downstream
    analysis can drop or widen those cases rather than treating 1970 as
    1 January 1970.
    """
    if raw is None:
        return ParsedDate(None, "unknown", "")
    original = str(raw).strip()
    if not original:
        return ParsedDate(None, "unknown", "")

    text = normalize_text(original)

    m = _ISO.search(text)
    if m:
        try:
            return ParsedDate(date(*map(int, m.groups())), "day", original)
        except ValueError:
            pass

    # Truncated ISO ("1974-01") occurs where a source gives only month and
    # year. Reported at month precision, not padded up to a false day.
    m = _YEAR_MONTH.fullmatch(text)
    if m:
        year, month = map(int, m.groups())
        return ParsedDate(date(year, month, 1), "month", original)

    m = _DMY_NUM.search(text)
    if m:
        day, month, year = map(int, m.groups())
        try:
            return ParsedDate(date(year, month, day), "day", original)
        except ValueError:
            pass

    # "6 novembre 1970" / "٦ نوفمبر ١٩٧٠" / "November 6, 1970"
    for name, num in sorted(_ALL_MONTHS.items(), key=lambda kv: -len(kv[0])):
        if name not in text:
            continue
        year_m = _YEAR_ONLY.search(text)
        if not year_m:
            continue
        year = int(year_m.group(1))
        day_m = re.search(rf"(\d{{1,2}})\s*(?:er\s*)?{re.escape(name)}", text)
        if not day_m:
            day_m = re.search(rf"{re.escape(name)}\s*(\d{{1,2}})\b", text)
        if day_m:
            try:
                return ParsedDate(date(year, num, int(day_m.group(1))), "day", original)
            except ValueError:
                pass
        return ParsedDate(date(year, num, 1), "month", original)

    m = _YEAR_ONLY.search(text)
    if m:
        return ParsedDate(date(int(m.group(1)), 1, 1), "year", original)

    return ParsedDate(None, "unknown", original)


def date_overlap_days(
    a_start: date | None, a_end: date | None,
    b_start: date | None, b_end: date | None,
    censor: date | None = None,
) -> int:
    """Days of overlap between two tenures, 0 if they never coincide.

    Open ends (`None`) are censored at `censor` (default: the pipeline
    snapshot date) so that incumbents get finite, reproducible durations.
    """
    censor = censor or config.snapshot_date()
    if a_start is None or b_start is None:
        return 0
    a_end = a_end or censor
    b_end = b_end or censor
    latest_start = max(a_start, b_start)
    earliest_end = min(a_end, b_end)
    return max(0, (earliest_end - latest_start).days)


def iter_unique(items: Iterable[str]) -> list[str]:
    """Order-preserving dedup, used when merging name variants."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
