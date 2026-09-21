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
Latin column is the only one that covers the roster. Reducing it to consonants
is what makes it comparable with an Arabic register; see `surname_spine.py`.
The 562 with both are written out with both spines, which is not redundancy:
the analysis uses them as a held-out check on the bridge, on ministers rather
than on the literary notables the bridge was validated against.

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
    from .surname_spine import is_arabic, family_candidates, spine, spine_variants
except ImportError:                                      # run as a bare script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from surname_spine import is_arabic, family_candidates, spine, spine_variants

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "elite_persistence"

PERSONS = PROCESSED / "persons.csv"
APPOINTMENTS = PROCESSED / "appointments.csv"

LAYER = "ministers"

LAYER_FIELDS = [
    "layer", "person_id", "name_raw", "script",
    "surname_candidates", "spine_candidates", "period", "subgroup",
    "name_ar", "spine_candidates_ar", "first_year", "max_rank_level",
    "ever_head_of_government", "birth_governorate",
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


def build() -> list[dict]:
    persons = {r["person_id"]: r for r in _read(PERSONS)}
    appointments = _read(APPOINTMENTS)
    eras = eras_by_person(appointments)

    rows = []
    for pid, p in sorted(persons.items()):
        name = (p["name"] or "").strip()
        if not name:
            continue
        cands = family_candidates(name)
        keys = [spine(c) for c in cands]
        name_ar = (p["name_ar"] or "").strip()
        ar_keys = [spine(c) for c in family_candidates(name_ar)] if name_ar else []
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
                "spine_candidates": "|".join(keys),
                "period": era,
                "subgroup": p["birth_governorate"] or "",
                "name_ar": name_ar,
                "spine_candidates_ar": "|".join(ar_keys),
                "first_year": (p["first_appointment"] or "")[:4],
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
    # The bridge check the Arabic column exists for: where a minister is named
    # in both scripts, does reducing the French name reach the Arabic one? This
    # is the figure quoted in EliteNetworksTN's VALIDATION-persistence.md, and
    # it is a harder test than the A'lam gate, which compares whole names.
    checkable = {r["person_id"]: r for r in rows if r["spine_candidates_ar"]}
    plain = agree = 0
    for r in checkable.values():
        ar = set(r["spine_candidates_ar"].split("|"))
        cands = r["surname_candidates"].split("|")
        plain += bool(set(r["spine_candidates"].split("|")) & ar)
        variants = set().union(*[spine_variants(c) for c in cands]) if cands else set()
        agree += bool(variants & ar)
    by_era = collections.Counter(r["period"] for r in rows)

    print(f"wrote {path.relative_to(ROOT)}")
    print(f"  {len(rows):,} person-era rows over {len(people):,} ministers")
    print(f"  {len(checkable):,} named in Arabic as well as Latin; of those the "
          f"French name reduces to the Arabic one for")
    print(f"    {plain / len(checkable):>6.1%} on the plain reading, "
          f"{agree / len(checkable):.1%} allowing the licensed variants")
    print("  by era:")
    for era, n in by_era.most_common():
        print(f"    {era or '(undated)':<20} {n:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
