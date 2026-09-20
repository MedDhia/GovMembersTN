"""Surname matching across scripts, for the elite-persistence comparison.

The comparison this module exists for sets four elite rosters against one
baseline, and the five are not written in one script. The electoral register,
the parliamentarians and the ministers are Arabic. The genealogies, the CMF
filings and the JORT company notices are Tunisian French. A surname has to
mean the same thing in all five or nothing downstream is a comparison.

**The reduction.** Arabic does not write short vowels, so a Latin form of a
Tunisian surname supplies them by convention and two conventions rarely agree:
``مزالي`` is *Mzali* in the press and *Mezali* out of a rule-based
transliterator; ``درغوث`` is *Darghouth* and *Drghouth*; ``النيفر`` is
*Ennaifer* and *Nifr*. Matching on the Latin string recovers a quarter of the
genealogical families. Matching on the consonants recovers 94.6% of them,
because the consonants are what the Arabic actually records.

``latin_spine`` and ``arabic_spine`` are lifted, unchanged in behaviour, from
``src/aalam/romanise.py`` in this repository, where they gate every French
gloss in the A'lam build against the Arabic it claims to render. ``spine.py``
is standalone and stdlib-only so the same file can be copied into
ElectionsTN, GovMembersTN and ParliamentariansTN, which have no package in
common with this one; ``tests/test_persistence_spine.py`` asserts this copy
still agrees with the original on every name in the A'lam register, so the
copies cannot drift silently.

**What is added here** is surname-level, and the gate never needed it. A full
name carries three or four tokens and the redundancy between them settles most
ambiguity; a bare surname carries one, so this module also has to say when a
spine is too short to mean anything (`tier`), and how to find the surname
inside an Arabic full name in the first place (`family_candidates`).
"""
from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------- #
# the Latin side
# --------------------------------------------------------------------------- #

# Digraphs first, longest first, or `sh` inside `Achour` would resolve as A-C-H.
# French and English spell the same Arabic consonant differently (`ch` against
# `sh`, `dj` against `j`), so both spellings fold to one class.
_DIGRAPHS = [
    ("sch", "S"),
    ("kh", "X"), ("gh", "V"), ("dh", "D"), ("th", "T"), ("sh", "S"),
    ("ch", "S"), ("dj", "J"), ("ph", "F"),
]

# `عبد الجليل` is `Abd al-Jalil` with the article written out and `Abdeljelil`
# with it swallowed into the word. Both are the same name.
_COMPOUND = re.compile(r"\babd[\s-]*[ae]l[\s-]*", re.I)

# Written in Latin, never present in the Arabic skeleton: the short vowels the
# script omits, and the matres lectionis, which surface in Latin as any vowel
# at all (`بو` is Bou, Bu, Bo).
_VOWELS = set("AEIOUWY")

# The article, on both sides. Arabic prefixes it to the word; Latin writes it
# al-, el-, ez-, es-, ech- (assimilated to a sun letter) or drops it outright.
_LATIN_ARTICLE = re.compile(
    r"\b(?:al|el|ad|ar|as|az|ech|esh|ez|es|er|ed)[-\s]", re.I)
_LATIN_PROCLITIC = re.compile(r"\b(b|l)(?:il|i[-\s]*al|i[-\s]*el)[-\s]", re.I)
_FRENCH_ARTICLE = re.compile(r"^\s*(?:(?:la|le|les)\s+|l['’])", re.I)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def _squeeze(spine: str) -> str:
    """Collapse a doubled consonant: `Khereddine` and `Khayr al-Din` are one name."""
    out: list[str] = []
    for ch in spine:
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)


def _labial(spine: str) -> str:
    """`حانبة` is written Hanba and said Hamba; French spells what is said."""
    return re.sub(r"N(?=[BM])", "M", spine)


# `th` and `dh` are the two Latin digraphs that are also a legal pair of single
# letters: `th` is ث in `Othmana` but ت followed by ح in `Fathallah`.
AMBIGUOUS_DIGRAPHS = ("th", "dh")


def latin_spine(text: str, *, split: tuple = ()) -> str:
    """The consonants of a Latin name, with everything the Arabic omits removed.

    Digraphs named in ``split`` are read as two letters rather than one.
    """
    s = _strip_accents(text or "").lower()
    s = _FRENCH_ARTICLE.sub("", s)
    s = _COMPOUND.sub("abd ", s)
    s = _LATIN_PROCLITIC.sub(r"\1 ", s)
    s = _LATIN_ARTICLE.sub(" ", s)
    # Before the digraphs, because the class marker for غ is v and this would
    # otherwise rewrite it: Ghattas would come back Fattas.
    s = s.replace("v", "f")
    for src, dst in _DIGRAPHS:
        if src not in split:
            s = s.replace(src, dst.lower())
    # French g is two consonants. Before a front vowel it is the sound of ج;
    # elsewhere, and in the digraph gu, it is the hard g that Tunisian French
    # writes for ق (Bourguiba is بورقيبة).
    s = re.sub(r"gu(?=[eiy])", "k", s)
    s = re.sub(r"g(?=[eiy])", "j", s)
    s = s.replace("g", "k")
    s = re.sub(r"c(?=[eiy])", "s", s)
    s = s.replace("c", "k").replace("ç", "s").replace("q", "k")
    # Arabic has no p and no v; it writes ب and ف for them.
    s = s.replace("p", "b")
    s = re.sub(r"[^a-z]", "", s)
    s = "".join(c for c in s.upper() if c not in _VOWELS)
    return _squeeze(_labial(s))


# --------------------------------------------------------------------------- #
# the Arabic side
# --------------------------------------------------------------------------- #

_HARAKAT = re.compile(r"[ً-ْٰٟۖ-ۭ]")
_TATWEEL = "ـ"

# One letter, one class, no ambiguity: the spine reads the Arabic letters
# directly rather than folding a transliteration, so a د followed by a ه stays
# distinguishable from a single ذ.
_ARABIC_CLASS = {
    "ب": "B", "ت": "T", "ث": "T", "ج": "J", "ح": "H", "خ": "X",
    "د": "D", "ذ": "D", "ر": "R", "ز": "Z", "س": "S", "ش": "S",
    "ص": "S", "ض": "D", "ط": "T", "ظ": "Z", "غ": "V", "ف": "F",
    "ق": "K", "ك": "K", "ل": "L", "م": "M", "ن": "N", "ه": "H",
    # The Tunisian letters for a hard g and a p.
    "ڤ": "K", "ڨ": "K", "ﭬ": "K", "پ": "B", "چ": "J",
    # Written, not sounded as a consonant: the long vowels, the glottals the
    # Latin forms drop, and the diacritics.
    "ا": "", "أ": "", "إ": "", "آ": "", "و": "", "ي": "", "ى": "",
    "ء": "", "ئ": "", "ؤ": "", "ة": "",
}

# Only the article is removed: the ب of `بالقاهرة` is a preposition and a
# consonant the Latin form writes, so stripping the pair whole would make every
# correct reading fail.
_AR_PROCLITIC = [(re.compile(r"(?:^|(?<=[\s(\[«]))بال"), "ب"),
                 (re.compile(r"(?:^|(?<=[\s(\[«]))لل"), "ل"),
                 (re.compile(r"(?:^|(?<=[\s(\[«]))(?:وال|ال)"), " ")]


def strip_harakat(text: str) -> str:
    """Drop vowel marks. They are optional in print and inconsistent in OCR."""
    return _HARAKAT.sub("", (text or "").replace(_TATWEEL, ""))


def arabic_spine(text: str) -> str:
    """The consonants of an Arabic string, by the same reduction as the Latin.

    This is the gate's reduction, unchanged. Use ``surname_spine`` for a bare
    surname; see the note there for the one rule that has to differ.
    """
    s = strip_harakat(text)
    for pattern, repl in _AR_PROCLITIC:
        s = pattern.sub(repl, s)
    out = "".join(_ARABIC_CLASS.get(ch, "") for ch in s)
    return _squeeze(_labial(out))


# `وال` at the head of a *sentence fragment* is the conjunction plus the
# article -- `والشيخ`, and-the-shaykh -- and the gate strips it. At the head of
# a *surname* it is neither: no Tunisian surname begins with the conjunction,
# and 2,408 voters are registered as `والي`, Ouali, which the rule reduces to
# nothing at all. The same eats `وسلاتي` (Oueslati) and `ورداني` (Ourdani). So
# the surname reduction drops that rule and keeps the article rule, which still
# has to fire on a *later* token as well as the first: `عبد الحفيظ` is one
# surname of two words and the article inside it is an article.
# `بال` and `لل` go with it, and for the same reason. In running text they are
# a preposition fused to the article and the gate strips the article out of
# them; at the head of a surname `بال` is the particle *Bel*, and its lam is
# part of the name -- `بالحاج` is Belhaj, BLHJ, not BHJ.
_AR_PROCLITIC_SURNAME = [(re.compile(r"(?:^|(?<=\s))ال"), " ")]


# A word-final ه is a ta marbuta written without its dots, and the electoral
# register writes it that way constantly: `بلخوجه` and `بالخوجه` hold 556 voters
# between them, `بلخوجة` holds 57, and they are one family. The letter table
# deletes ة and keeps ه as a consonant, so the two spellings reduce to BLXJ and
# BLXJH and never meet -- which understates the baseline for exactly the rare
# notable surnames this build is about, and so overstates their
# over-representation by an order of magnitude. Final ه is therefore read as ة.
# The cost is `الله`, where the ه is sounded and French writes it; the Latin
# side answers that by offering a reading with the final H dropped.
_FINAL_HA = re.compile(r"ه(?=\s|$)")


def arabic_surname_spine(text: str) -> str:
    """The consonants of an Arabic surname."""
    s = _FINAL_HA.sub("ة", strip_harakat(text))
    for pattern, repl in _AR_PROCLITIC_SURNAME:
        s = pattern.sub(repl, s)
    out = "".join(_ARABIC_CLASS.get(ch, "") for ch in s)
    return _squeeze(_labial(out))


def spine(text: str) -> str:
    """The spine of a surname in either script, chosen by what the string is.

    The script has to be read off the string rather than off the source: the
    electoral register is Arabic, but its diaspora rows are registered in Latin
    and 33,758 of its surnames are spelled that way. Reducing those as Arabic
    returns nothing, which silently drops 4.9% of the denominator.
    """
    return arabic_surname_spine(text) if is_arabic(text) else latin_spine(text)


_ARABIC_RANGE = re.compile(r"[؀-ۿݐ-ݿ]")


def is_arabic(text: str) -> bool:
    return bool(_ARABIC_RANGE.search(text or ""))


# --------------------------------------------------------------------------- #
# what a Latin spelling leaves open
# --------------------------------------------------------------------------- #

# The Arabic is the authority: a registered surname has one spelling and one
# spine, and the index is built on it. The ambiguity is all on the Latin side,
# where one French spelling can render two different Arabic strings, so the
# *query* is what carries variants. Indexing the variants instead would put the
# same surname in several buckets and count its voters more than once.
#
# Three ambiguities account for nearly every Latin surname that fails to find
# its Arabic form, measured on the 562 ministers this repository names in both
# scripts:
#
#   the fused article   Tunisian French writes the article onto the surname as a
#                       bare L -- `Laroussi` is العروسي, `Larayedh` is العريض,
#                       `Labidi` is العبيدي. It cannot simply be stripped,
#                       because `Lakhoua` and `Louati` begin with a real lam,
#                       so both readings are offered.
#   dh for ظ            French writes ظ as `dh` as often as `z`: `Mahfoudh` is
#                       محفوظ and `M'dhaffer` is المظفر, and the letter table
#                       maps ظ to Z, so the plain reading never matches.
#   th, dh as two       `Mathari` is المطهري, a ط followed by a ه, not a ث.
#
_FUSED_ARTICLE = re.compile(r"^\s*l(?=[aeiouy])", re.I)


def latin_spine_variants(text: str) -> set[str]:
    """Every spine a Latin surname is allowed to reduce to.

    The plain reading first; then the readings the three ambiguities above
    license, and their combinations. A caller matches against an index of
    Arabic spines and keeps the first variant that is attested.
    """
    readings = {text}
    fused = _FUSED_ARTICLE.sub("", text or "")
    if fused != (text or ""):
        readings.add(fused)
    # ظ, which the letter table calls Z and French calls dh.
    readings |= {r.replace("dh", "z").replace("DH", "Z") for r in list(readings)
                 if "dh" in r.lower()}
    out = set()
    for reading in readings:
        for split in ((), ("th",), ("dh",), AMBIGUOUS_DIGRAPHS):
            key = latin_spine(reading, split=split)
            if key:
                out.add(key)
    # The Arabic side reads a word-final ه as a ta marbuta and deletes it, so a
    # Latin form that writes the h -- `Abdallah`, `Bouchamaoui`'s `Fakhfakh` --
    # has to offer the reading without it.
    out |= {k[:-1] for k in list(out) if k.endswith("H") and len(k) > 1}
    return out


def spine_variants(text: str) -> set[str]:
    """Every spine a surname in either script is allowed to reduce to.

    Arabic is unambiguous here and returns a single reading; see above.
    """
    if is_arabic(text):
        key = arabic_surname_spine(text)
        return {key} if key else set()
    return latin_spine_variants(text)


# --------------------------------------------------------------------------- #
# finding the surname inside a name
# --------------------------------------------------------------------------- #

# A Tunisian name runs given - father - (grandfather) - family, and the family
# part may be one token or two (`بن ميلاد`, `أولاد علي`, `بو عبد الله`). The
# surname is therefore the last token plus however many particles bind onto its
# left, and no further: offering every suffix instead looks safer and is not,
# because the spine space is dense enough that a wrong one matches. `ليلى أولاد
# علي` reduces whole to LDL, which the register attests, so a caller taking the
# longest attested suffix files Leila Ouled Ali under her given name.
_AR_SURNAME_PARTICLES = {
    "بن", "ابن", "إبن", "بنت", "بو", "أبو", "ابو", "أبي", "ابي",
    "أولاد", "اولاد", "ولد", "أولد", "اولد", "بل", "بلحاج",
    "عبد", "بوعبد", "دو", "دي", "باش", "بالش", "شيخ",
}

# These bind *leftwards*, onto the token before them, which every other
# particle does the opposite of. `شرف الدين` is Charfeddine and `نور الدين` is
# Noureddine: one name of two words, and reading the last word alone files both
# men under al-Din, which is not a surname and which the register does attest.
_AR_BOUND_SUFFIXES = {"الدين", "الله", "الرحمان", "الرحمن", "المولى"}

# In Tunisian French the same particles are printed detached from the surname
# and attached to the given name's side of the string -- `Mohamed Ben Salem` --
# so the last token alone loses what distinguishes `Ben Ayed` from `Ayed`, and
# the register lists both as separate families.
_LATIN_SURNAME_PARTICLES = {
    "BEN", "BENT", "BIN", "IBN", "BELHADJ", "BEL", "BOU", "ABOU", "ABU",
    "OULED", "OULAD", "OULD", "EL", "AL", "ES", "ECH", "EZ", "ED", "ER",
    "DE", "DI", "DA", "ABD", "ABDEL", "ABDE",
}

# `سيدي` and `SIDI` are in neither set on purpose: they are honorifics here,
# stripped before the walk ever runs, and a token cannot be both.

# Titles and honorifics that are printed with the name on a candidate list or
# in a gazette notice and are not part of it. They are stripped everywhere
# *except* in final position, because several of them are also surnames and
# that is where a surname sits: `عبد الحميد الشيخ` is Abdelhamid Escheikh, and
# a rule that strips الشيخ wherever it appears files him under his father.
_AR_HONORIFICS = {
    "الدكتور", "دكتور", "د", "الأستاذ", "الاستاذ", "أستاذ", "استاذ", "الأستاذة",
    "الاستاذة", "السيد", "السيدة", "المرحوم", "الحاج", "الحاجة", "المهندس",
    "الشيخ", "مولاي", "سيدي", "الجنرال", "العميد", "القائد",
}
_LAT_HONORIFICS = {
    "M", "MR", "MME", "MLLE", "MONSIEUR", "MADAME", "MADEMOISELLE", "DR",
    "PR", "PROF", "ME", "MAITRE", "FEU", "SI", "HAJ", "HADJ", "SIDI",
    "GENERAL", "COLONEL", "COMMANDANT", "S", "SES", "LEURS",
}

_AR_WS = re.compile(r"[\s ‏‎]+")
_AR_PUNCT = re.compile(r"[^؀-ۿ\s]")

# A parenthesis after a name is a disambiguator and not part of it: the
# ministers table carries `سمير سعيد (وزير)` and `النوري السالمي (سياسي)`,
# where the bracket says *minister* and *politician*. Stripping the brackets
# and keeping their contents, which is what removing punctuation alone does,
# files both men under the word for their job.
_PARENTHETICAL = re.compile(r"[(（\[].*?[)）\]]")


def arabic_tokens(name: str) -> list[str]:
    """Arabic-script tokens of a name, honorifics and printer's marks removed."""
    cleaned = _AR_PUNCT.sub(" ", _PARENTHETICAL.sub(" ", strip_harakat(name or "")))
    toks = [t for t in _AR_WS.split(cleaned) if t]
    return _bind_suffixes(_drop_honorifics(toks, _AR_HONORIFICS),
                          _AR_BOUND_SUFFIXES)


def _drop_honorifics(toks: list[str], honorifics: set[str]) -> list[str]:
    """Remove titles, but never the last token: that is where a surname sits."""
    if not toks:
        return toks
    kept = [t for t in toks[:-1] if t not in honorifics]
    return kept + [toks[-1]]


def _bind_suffixes(toks: list[str], bound: set[str]) -> list[str]:
    """Fuse a leftward-binding token onto the one before it."""
    out: list[str] = []
    for tok in toks:
        if tok in bound and out:
            out[-1] = f"{out[-1]} {tok}"
        else:
            out.append(tok)
    return out


def latin_tokens(name: str) -> list[str]:
    """Latin tokens of a name, honorifics removed, hyphens read as spaces."""
    cleaned = _strip_accents(_PARENTHETICAL.sub(" ", name or "")).upper()
    cleaned = cleaned.replace("-", " ").replace("_", " ")
    cleaned = re.sub(r"[^A-Z' ]+", " ", cleaned)
    return _drop_honorifics([t for t in cleaned.split() if t], _LAT_HONORIFICS)


def _walk_particles(toks: list[str], particles: set[str]) -> list[str]:
    """The last token, then it with each binding particle added, longest first."""
    if not toks:
        return []
    out = [toks[-1]]
    i = len(toks) - 2
    while i >= 0 and toks[i] in particles:
        out.append(" ".join(toks[i:]))
        i -= 1
    out.reverse()
    return out


def family_candidates(name: str) -> list[str]:
    """Suffixes of a full name that could be the surname, longest first.

    The caller resolves them against the register and keeps the first that is
    attested, so ``علي بن سالم`` yields ``بن سالم`` where that is a surname and
    falls back to ``سالم`` where it is not. Only particles bind: a given name is
    never offered as part of the surname, whatever the register would match.
    """
    if is_arabic(name):
        return _walk_particles(arabic_tokens(name), _AR_SURNAME_PARTICLES)
    return _walk_particles(latin_tokens(name), _LATIN_SURNAME_PARTICLES)


def latin_family_candidates(name: str) -> list[str]:
    """``family_candidates`` for a name already known to be Latin."""
    return _walk_particles(latin_tokens(name), _LATIN_SURNAME_PARTICLES)


# --------------------------------------------------------------------------- #
# how much a spine is worth
# --------------------------------------------------------------------------- #

# Deleting the vowels costs discrimination, and it costs most on short names.
# `Bouchoucha`, `Bouchouicha` and `Bechicha` are one spine (BS); so are `Sassi`,
# `Souissi`, `Ayachi` and `Aissaoui` (S). A two-letter spine is not a surname,
# it is a class of surnames, and the headline estimates are restricted to
# spines long enough to name a family. Three letters is the floor: it is where
# the median spine stops absorbing more than one register surname.
MIN_INFORMATIVE_LEN = 3

# A spine may be long and still pool several distinct registered surnames.
# `tier` reports both facts; the analysis decides what to do with them.
TIER_NAMED = "named"          # long enough, and one register surname dominates
TIER_POOLED = "pooled"        # long enough, but several surnames share it
TIER_SHORT = "short"          # too short to name a family at all

# The share of a spine's voters that the largest single register surname must
# hold for the spine to be read as naming that surname.
DOMINANCE = 0.80


def tier(spine_key: str, n_surnames: int, dominant_share: float) -> str:
    """Classify a spine by whether it can stand for one family.

    ``n_surnames`` and ``dominant_share`` are read off the electoral register,
    which is the only source large enough to say how many distinct surnames a
    spine pools and in what proportion.
    """
    if len(spine_key) < MIN_INFORMATIVE_LEN:
        return TIER_SHORT
    if n_surnames == 1 or dominant_share >= DOMINANCE:
        return TIER_NAMED
    return TIER_POOLED
