"""02 - Territorial representation: recompute the Gini from the raw tables.

    python analysis/python/02_representation_gini.py

This deliberately does NOT read data/processed/indices/representation_gini.csv,
and does not import `govtn.inequality`. It rebuilds the index from
persons.csv, appointments.csv and governorates.csv with pandas alone, then
checks its own answer against the published file - so it is a reproduction test
of the published numbers rather than a re-display of them.

`analysis/R/02_representation_gini.R` is the same computation in base R.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from load_govtn import load  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "output" / "tables"
OUT.mkdir(parents=True, exist_ok=True)

persons = load("persons")
appointments = load("appointments")
governorates = load("governorates")


def representation_gini(counts: dict, populations: dict) -> float | None:
    """Gini of the Lorenz curve of population share against minister share.

    Governorates that supplied NO minister must stay in: they still consume
    their share of the population along the curve, and they are precisely the
    cases the measure exists to capture. Dropping them understates inequality.
    """
    total_pop = sum(populations.values())
    total_min = sum(counts.get(name, 0) for name in populations)
    if not total_pop or not total_min:
        return None
    order = sorted(populations, key=lambda n: counts.get(n, 0) / populations[n])
    x = y = 0.0
    area = 0.0
    for name in order:
        dx = populations[name] / total_pop
        dy = counts.get(name, 0) / total_min
        area += dx * (y + (y + dy)) / 2      # trapezoid
        x += dx
        y += dy
    return 1 - 2 * area


# The level of this index is only defined relative to a partition, and
# Tunisia's have moved: Ariana and Ben Arous were split off Greater Tunis in
# 1983 and Manouba in 2000, after most of these ministers were born. Compute
# all three; the trend is what survives.
GREATER_TUNIS = {"Tunis", "Ariana", "Ben Arous", "Manouba"}
UNITS = ["governorate", "greater_tunis_merged", "region"]
ERAS = ["protectorate", "bourguiba", "ben_ali", "transition", "second_republic"]

region_of = dict(zip(governorates.governorate, governorates.region_type))
pop_of = dict(zip(governorates.governorate, governorates.population))


def unit_of(name: str, units: str) -> str:
    if units == "governorate":
        return name
    if units == "greater_tunis_merged":
        return "Greater Tunis" if name in GREATER_TUNIS else name
    if units == "region":
        return region_of[name]
    raise ValueError(f"unknown units {units!r}")


def unit_populations(units: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, population in pop_of.items():
        key = unit_of(name, units)
        out[key] = out.get(key, 0) + int(population)
    return out


# One row per person per era: a minister serving under two regimes counts in
# each, matching the convention used throughout the dataset.
pairs = (appointments[["person_id", "era"]].dropna().drop_duplicates()
         .merge(persons[["person_id", "birth_governorate"]], on="person_id"))
coded = pairs[pairs.birth_governorate.notna()]

rows = []
for units in UNITS:
    populations = unit_populations(units)
    for era in ERAS:
        block = coded[coded.era == era]
        counts: dict[str, float] = {}
        for name in block.birth_governorate:
            key = unit_of(name, units)
            counts[key] = counts.get(key, 0) + 1
        rows.append({"units": units, "era": era, "coded": len(block),
                     "gini": representation_gini(counts, populations)})
result = pd.DataFrame(rows)

wide = result.pivot(index="era", columns="units", values="gini").reindex(ERAS)
print("Gini of ministerial representation, by era and partition\n")
print(wide.round(3).to_string())
result.to_csv(OUT / "02_representation_gini_recomputed.csv", index=False)

# --- Check against the published file --------------------------------------
published = load("representation_gini")
published = published[published.era.isin(ERAS) & published.gini_representation.notna()]
merged = result.merge(published[["units", "era", "gini_representation"]],
                      on=["units", "era"])
assert len(merged) == len(result), "published file is missing rows we computed"
worst = (merged.gini - merged.gini_representation).abs().max()
print(f"\nAgreement with data/processed/indices/representation_gini.csv: "
      f"max |diff| = {worst:.2e}")
# The published file rounds to 4 decimal places, so the most two identical
# implementations can agree is 5e-5. A tighter tolerance would fail on the
# rounding rather than on any real disagreement.
if worst > 1e-4:
    raise SystemExit("recomputed index does not match the published file")
print("Reproduced, to the precision the published file is rounded to.")
