"""The ministers, reduced to surnames, for the elite-persistence comparison.

The comparison is assembled in EliteNetworksTN and asks whether the families
the Tunisian genealogies record hold office out of proportion to their share of
the population, and whether that has survived the changes of regime. The
denominator is the 2024 electoral register, built in ElectionsTN. This module
supplies one of the numerators: everyone who has held ministerial rank.

Why one row per person per era
------------------------------
The question is about persistence, so the unit that matters is not the minister
but the minister *in a regime*. A person who served Bourguiba and then Ben Ali
is evidence about both, and counting them once would make the earlier regime
look emptier than it was. So a person appears once for each era they held
office in, taken from the eras their appointments fall in rather than from
`persons.eras_served`, which is a derived string. Deduplicate on `person_id`
for a headcount.

Why the Latin name and not the Arabic one
-----------------------------------------
`persons.csv` names all 882 people in Latin and 562 of them in Arabic, so the
Latin column is the only one that covers the roster. EliteNetworksTN reads it
against the Arabic register through its Arabic-Latin surname crosswalk
(`src/surname_crosswalk`), which says which registered Arabic surname each
Latin spelling renders. The 562 with both names are written with both, which
is not redundancy: the crosswalk learns from them how Tunisian surnames are
spelled in Latin letters, and is tested on them.

What is written
---------------
`data/processed/elite_persistence/layer_ministers.csv`, in the schema the four
repositories share. Surnames are written as *candidates*, longest first, rather
than resolved: only the register can say whether `Ben Ayed` is a family in its
own right or a patronymic, and this repository does not hold the register.

`data/processed/elite_persistence/layer_minister_appointments.csv`, one row per
person and government from independence on, with the government's head, the
head of the executive who appointed it and the ruling coalition behind it. It
lets EliteNetworksTN ask whether the ruler or the coalition decides who enters
the cabinet. Heads of government themselves are left out: they are the
appointers, not the appointed.

Three pre-independence cabinets carry misdated copies
------------------------------------------------------
`appointments.csv` files the cabinets of Slaheddine Baccouche (1943, 1952) and
of Mohamed Salah Mzali (1954) under the spells of Hedi Baccouche (1987) and of
Mohamed Mzali (1980), because the build matches a cabinet article to a spell by
the head's surname. Each member therefore appears twice: once at the cabinet's
own date and once at the later spell's start. The later copies -- 29 rows over
24 people -- would count the ministers of the 1940s and 1950s as ministers of
Bourguiba's 1980s and of Ben Ali, so both files drop them (`MISDATED`). Eleven
of the 24 exist only in those copies: the Arabic article's names, which
reconciliation never joined to the French ones (Mohamed Hadjouj is also
محمد حجوج), so they are second entries for men already in the roster and are
left out of it.

Run with::

    python3 -m govtn.elite_persistence          # or: make elite-persistence

Standard library only, about a second, byte-identical on every run.
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

try:
    from .surname_spine import is_arabic, family_candidates
except ImportError:                                      # run as a bare script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from surname_spine import is_arabic, family_candidates

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "elite_persistence"

PERSONS = PROCESSED / "persons.csv"
APPOINTMENTS = PROCESSED / "appointments.csv"

LAYER = "ministers"

# The copies described in the module docstring: these cabinets' rows dated at
# the start of the spell the build wrongly matched them to.
MISDATED = {
    "Gouvernement Slaheddine Baccouche I": "1987-11-07",
    "Gouvernement Slaheddine Baccouche II": "1987-11-07",
    "Gouvernement Mohamed Salah Mzali": "1980-04-23",
}

# Four Saied-era governments filed as one, every row dated 1 January 2021. The
# Arabic articles list the same governments one by one with usable dates, so
# the lumped rows are left out of the appointments file (they stay in the
# ministers' layer, where only their era is read, and it is right).
LUMPED = "Gouvernement Bouden/Hachani/Madouri/Zaafrani"

# Who appointed each government, and with which ruling coalition behind it.
# Under Bourguiba, Ben Ali and, from 25 July 2021, Saied the president chose
# the ministers whoever was prime minister; from 2011 to 2021 the head of
# government formed the cabinet. Two spells cross a rupture and are split at
# it: Ghannouchi's at 14 January 2011, after which he formed the interim
# governments of 17 and 27 January, and Mechichi's at 25 July 2021, after which
# Saied governed by decree until Bouden's government of 11 October.
# (spell, from, government, head of the executive, coalition)
GOVERNMENTS = [
    ("TN-01", "1956-04-15", "TN-01", "Habib Bourguiba", "Neo-Destour"),
    ("TN-02", "1957-07-29", "TN-02", "Habib Bourguiba", "Neo-Destour/PSD"),
    ("TN-03", "1969-11-07", "TN-03", "Habib Bourguiba", "Neo-Destour/PSD"),
    ("TN-04", "1970-11-02", "TN-04", "Habib Bourguiba", "Neo-Destour/PSD"),
    ("TN-05", "1980-04-23", "TN-05", "Habib Bourguiba", "Neo-Destour/PSD"),
    ("TN-06", "1986-07-08", "TN-06", "Habib Bourguiba", "Neo-Destour/PSD"),
    ("TN-07", "1987-10-02", "TN-07", "Habib Bourguiba", "Neo-Destour/PSD"),
    ("TN-08", "1987-11-07", "TN-08", "Zine El Abidine Ben Ali", "RCD"),
    ("TN-09", "1989-09-27", "TN-09", "Zine El Abidine Ben Ali", "RCD"),
    ("TN-10", "1999-11-17", "TN-10", "Zine El Abidine Ben Ali", "RCD"),
    ("TN-10", "2011-01-14", "TN-10b", "Mohamed Ghannouchi", "Interim, 2011"),
    ("TN-11", "2011-02-27", "TN-11", "Beji Caid Essebsi", "Interim, 2011"),
    ("TN-12", "2011-12-24", "TN-12", "Hamadi Jebali", "Troika"),
    ("TN-13", "2013-03-13", "TN-13", "Ali Larayedh", "Troika"),
    ("TN-14", "2014-01-29", "TN-14", "Mehdi Jomaa", "Technocrats"),
    ("TN-15", "2015-02-06", "TN-15", "Habib Essid", "Nidaa-Ennahda"),
    ("TN-16", "2016-08-27", "TN-16", "Youssef Chahed", "Nidaa-Ennahda"),
    ("TN-17", "2020-02-27", "TN-17", "Elyes Fakhfakh", "Ennahda-backed"),
    ("TN-18", "2020-09-02", "TN-18", "Hichem Mechichi", "Ennahda-backed"),
    ("TN-18", "2021-07-25", "TN-18b", "Kais Saied", "Presidential"),
    ("TN-19", "2021-10-11", "TN-19", "Kais Saied", "Presidential"),
    ("TN-20", "2023-08-01", "TN-20", "Kais Saied", "Presidential"),
    ("TN-21", "2024-08-07", "TN-21", "Kais Saied", "Presidential"),
    ("TN-22", "2025-03-21", "TN-22", "Kais Saied", "Presidential"),
]
INDEPENDENCE = "1956-04-15"

# A minister's party as the sources write it, in French or Arabic, to one
# name. Where a value records a change ("X puis Y"), the first party is the
# one the minister held when appointed.
PARTIES = [
    ("Ennahda", ("ennahdha", "ennahda", "النهضة")),
    ("Nidaa Tounes", ("nidaa", "نداء تونس")),
    ("CPR", ("cpr", "المؤتمر من أجل الجمهورية")),
    ("Ettakatol", ("ettakatol", "التكتل")),
    ("Afek Tounes", ("afek", "آفاق تونس")),
    ("UPL", ("union patriotique libre", "الاتحاد الوطني الحر")),
    ("Courant democrate", ("courant démocrate", "التيار الديمقراطي")),
    ("Tahya Tounes", ("tahya", "تحيا تونس")),
    ("Machrouu Tounes", ("machrouu",)),
    ("Mouvement du peuple", ("mouvement du peuple", "حركة الشعب")),
    ("RCD", ("rcd",)),
    ("PSD", ("psd",)),
    ("Neo-Destour", ("néo-destour", "neo-destour")),
    ("Independent", ("indépendant", "مستقل", "-")),
    ("Military", ("عسكري",)),
]

LAYER_FIELDS = [
    "layer", "person_id", "name_raw", "script",
    "surname_candidates", "period", "subgroup",
    "name_ar", "first_year", "years_in_office",
    "max_rank_level", "ever_head_of_government", "birth_governorate",
]

APPOINTMENT_FIELDS = [
    "person_id", "government", "government_head", "government_start",
    "head_of_executive", "coalition", "era", "first_date", "date_basis",
    "rank_level", "party", "first_since_independence", "served_before_independence",
]

# The era vocabulary is this repository's own (`data/processed/eras.csv`) and is
# written out unchanged. EliteNetworksTN maps it onto the shared periods; doing
# that here would push one repository's periodisation into another's data.
NO_ERA = ""


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_misdated(row: dict) -> bool:
    """A misdated copy of a pre-independence cabinet's member (docstring)."""
    return MISDATED.get(row["cabinet_id"]) == row["start_date"]


def party_of(raw: str) -> str:
    """The minister's party, as one name, or '' where the sources give none."""
    text = (raw or "").split(" puis ")[0].split(" / ")[0].strip().lower()
    if not text:
        return ""
    for name, needles in PARTIES:
        if any(text == n or (len(n) > 1 and n in text) for n in needles):
            return name
    return "Other"


def government_at(day: str) -> tuple | None:
    """The government in office on an ISO date, from independence on."""
    if not day or day < INDEPENDENCE:
        return None
    current = None
    for g in GOVERNMENTS:
        if g[1] <= day:
            current = g
    return current


def _precise(row: dict) -> bool:
    """Whether the start date is a day rather than a placeholder.

    A cabinet-level date of 1 January is how the build writes a year it could
    not place within the year, so it is not a day.
    """
    day = row["start_date"] or ""
    if len(day) != 10 or row["date_precision"] != "day":
        return False
    return not (row["date_basis"] == "cabinet" and day.endswith("-01-01"))


def government_of(row: dict) -> tuple | None:
    """The government an appointment belongs to.

    By its date where the date is a day; otherwise by the spell the build
    filed it under, Ghannouchi's and Mechichi's spells being split at their
    rupture by the era the row carries.
    """
    if _precise(row):
        return government_at(row["start_date"])
    spell = row["spell_id"]
    options = [g for g in GOVERNMENTS if g[0] == spell]
    if not options:
        return None
    if len(options) == 2 and row["era"] in ("transition", "saied_exception"):
        return options[1]
    return options[0]


def build_appointments(appointments: list[dict]) -> list[dict]:
    """One row per person and government from independence on.

    The appointments of heads of government are left out, and so are the
    misdated copies and the lumped Saied-era rows (module docstring). A person
    appointed several times within one government is written once, at the
    first appointment, with the highest rank held in it (the lowest level).
    """
    order = {g[2]: i for i, g in enumerate(GOVERNMENTS)}
    before = set()
    cells: dict[tuple, dict] = {}
    for r in appointments:
        if is_misdated(r) or r["cabinet_id"] == LUMPED or not r["person_id"]:
            continue
        if r["rank"] == "head_of_government":
            continue
        g = government_of(r)
        if g is None:
            if (r["start_date"] or "") and r["start_date"] < INDEPENDENCE:
                before.add(r["person_id"])
            continue
        key = (r["person_id"], g[2])
        day = r["start_date"] if _precise(r) else ""
        level = int(r["rank_level"]) if (r["rank_level"] or "").isdigit() else 9
        cell = cells.get(key)
        if cell is None:
            cells[key] = cell = {
                "person_id": r["person_id"], "government": g[2],
                "government_head": r["head_of_government"] if g[2] == g[0] else "",
                "government_start": g[1], "head_of_executive": g[3],
                "coalition": g[4], "era": r["era"], "first_date": day,
                "date_basis": "date" if day else "government",
                "rank_level": level, "parties": collections.Counter(),
            }
        if day and (not cell["first_date"] or day < cell["first_date"]):
            cell["first_date"], cell["date_basis"] = day, "date"
        cell["rank_level"] = min(cell["rank_level"], level)
        party = party_of(r["party_raw"])
        if party:
            cell["parties"][party] += 1
    heads = {}
    for r in appointments:
        if r["rank"] == "head_of_government" and r["spell_id"]:
            heads.setdefault(r["spell_id"], r["head_of_government"])
    first: dict[str, str] = {}
    for (pid, gov) in sorted(cells, key=lambda k: (k[0], order[k[1]])):
        first.setdefault(pid, gov)
    rows = []
    for (pid, gov), cell in sorted(cells.items(), key=lambda kv: (order[kv[0][1]], kv[0][0])):
        parties = cell.pop("parties")
        spell = next(g[0] for g in GOVERNMENTS if g[2] == gov)
        rows.append({
            **cell,
            "government_head": heads.get(spell, cell["government_head"]) if gov == spell
                               else {"TN-10b": "Mohamed Ghannouchi", "TN-18b": ""}[gov],
            "rank_level": cell["rank_level"] if cell["rank_level"] < 9 else "",
            "party": parties.most_common(1)[0][0] if parties else "",
            "first_since_independence": first[pid] == gov,
            "served_before_independence": pid in before,
        })
    return rows


def eras_by_person(appointments: list[dict]) -> dict[str, list[str]]:
    """Which eras each person held office in, in the order they first did.

    Read off the appointments rather than off `persons.eras_served` so that an
    appointment with no era -- 52 of 3,136 have none, for want of a usable date
    -- is visible as a gap rather than silently absorbed into a neighbour.
    """
    seen: dict[str, list[str]] = collections.defaultdict(list)
    for r in sorted(appointments, key=lambda a: (a["person_id"], a["start_date"] or "9999")):
        era = r["era"] or NO_ERA
        if era and era not in seen[r["person_id"]]:
            seen[r["person_id"]].append(era)
    return seen


def years_by_person(appointments: list[dict]) -> dict[str, list[int]]:
    """The calendar years each person held office in, by the recorded dates.

    An appointment counts in every year from the one it began in to the one it
    ended in. An appointment with no recorded end -- the government in office
    when the sources were read, or an end the build could not trust, 393 of
    3,136 -- counts in the year it began and in no other, so a gap in the
    record shortens a tenure rather than lengthening it. An appointment with no
    usable start counts nowhere, as it has no era.
    """
    years: dict[str, set[int]] = collections.defaultdict(set)
    for r in appointments:
        start = (r["start_date"] or "")[:4]
        if not start.isdigit():
            continue
        end = (r["end_date"] or "")[:4]
        first = int(start)
        last = int(end) if end.isdigit() else first
        years[r["person_id"]].update(range(first, max(first, last) + 1))
    return {pid: sorted(ys) for pid, ys in years.items()}


def build() -> list[dict]:
    persons = {r["person_id"]: r for r in _read(PERSONS)}
    every = _read(APPOINTMENTS)
    appointments = [r for r in every if not is_misdated(r)]
    # The people the misdated copies alone attest are second entries (module
    # docstring), so they leave the roster with their copies.
    kept = {r["person_id"] for r in appointments}
    phantoms = {r["person_id"] for r in every if is_misdated(r)} - kept
    persons = {pid: p for pid, p in persons.items() if pid not in phantoms}
    eras = eras_by_person(appointments)
    years = years_by_person(appointments)

    rows = []
    for pid, p in sorted(persons.items()):
        name = (p["name"] or "").strip()
        if not name:
            continue
        cands = family_candidates(name)
        name_ar = (p["name_ar"] or "").strip()
        # A person with no dated appointment still belongs to the roster; they
        # are written once, under the empty period, so the headcount is whole
        # and the period series does not quietly gain them.
        for era in eras.get(pid) or [NO_ERA]:
            rows.append({
                "layer": LAYER,
                "person_id": pid,
                "name_raw": name,
                "script": "ar" if is_arabic(name) else "lat",
                "surname_candidates": "|".join(cands),
                "period": era,
                "subgroup": p["birth_governorate"] or "",
                "name_ar": name_ar,
                "first_year": (p["first_appointment"] or "")[:4],
                "years_in_office": "|".join(str(y) for y in years.get(pid, [])),
                "max_rank_level": p["max_rank_level"],
                "ever_head_of_government": p["ever_head_of_government"],
                "birth_governorate": p["birth_governorate"],
            })
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = build()
    path = OUT / "layer_ministers.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LAYER_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    people = {r["person_id"] for r in rows}
    both = {r["person_id"] for r in rows if r["name_ar"]}
    by_era = collections.Counter(r["period"] for r in rows)

    apps = build_appointments(_read(APPOINTMENTS))
    apath = OUT / "layer_minister_appointments.csv"
    with apath.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=APPOINTMENT_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(apps)

    print(f"wrote {path.relative_to(ROOT)}")
    print(f"  {len(rows):,} person-era rows over {len(people):,} ministers")
    print(f"wrote {apath.relative_to(ROOT)}")
    print(f"  {len(apps):,} person-government rows over "
          f"{len({a['person_id'] for a in apps}):,} people, "
          f"{sum(a['first_since_independence'] for a in apps):,} first appointments")
    print(f"  {len(both):,} named in Arabic as well as Latin, for the crosswalk")
    print("  by era:")
    for era, n in by_era.most_common():
        print(f"    {era or '(undated)':<20} {n:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
