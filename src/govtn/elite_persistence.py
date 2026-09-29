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

LAYER_FIELDS = [
    "layer", "person_id", "name_raw", "script",
    "surname_candidates", "period", "subgroup",
    "name_ar", "first_year", "years_in_office",
    "max_rank_level", "ever_head_of_government", "birth_governorate",
]

# The era vocabulary is this repository's own (`data/processed/eras.csv`) and is
# written out unchanged. EliteNetworksTN maps it onto the shared periods; doing
# that here would push one repository's periodisation into another's data.
NO_ERA = ""


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


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
    appointments = _read(APPOINTMENTS)
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

    print(f"wrote {path.relative_to(ROOT)}")
    print(f"  {len(rows):,} person-era rows over {len(people):,} ministers")
    print(f"  {len(both):,} named in Arabic as well as Latin, for the crosswalk")
    print("  by era:")
    for era, n in by_era.most_common():
        print(f"    {era or '(undated)':<20} {n:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
