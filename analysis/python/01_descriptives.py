"""01 - Descriptives: what is in the dataset, and how much of it is missing.

    python analysis/python/01_descriptives.py

Needs pandas. Writes output/tables/01_*.csv. The R script
`analysis/R/01_descriptives.R` produces the same numbers.
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
cabinets = load("cabinets")

print("GovMembersTN")
print(f"  {len(persons)} persons, {len(appointments)} appointments, "
      f"{len(cabinets)} cabinets")
print(f"  appointments dated {appointments.start_date.min():%Y-%m-%d} to "
      f"{appointments.start_date.max():%Y-%m-%d}")

# --- 1. Attribute coverage -------------------------------------------------
# The first thing to look at in a dataset built from encyclopaedic sources.
# Every share computed below is conditional on these.
INTERESTING = ["birth_date", "birth_place", "birth_governorate", "gender",
               "education", "parties", "occupations", "wikidata_qid"]
coverage = pd.DataFrame({
    "variable": INTERESTING,
    "present": [int(persons[v].notna().sum()) for v in INTERESTING],
    "coverage": [float(persons[v].notna().mean()) for v in INTERESTING],
})
print("\nPerson-level coverage")
print(coverage.assign(coverage=lambda d: (d.coverage * 100).round().astype(int)
                      .astype(str) + "%").to_string(index=False))
coverage.to_csv(OUT / "01_attribute_coverage.csv", index=False)

# --- 2. Appointments per decade --------------------------------------------
# Catches silent holes: a seventy-year trend computed over a half-empty decade
# is a statement about the sources, not about Tunisia.
decade = (appointments.start_date.dt.year // 10 * 10).dropna().astype(int)
by_decade = (decade.value_counts().sort_index()
             .rename_axis("decade").reset_index(name="appointments"))
print("\nAppointments per decade")
print(by_decade.to_string(index=False))
by_decade.to_csv(OUT / "01_appointments_by_decade.csv", index=False)

# --- 3. Women in government, by era ----------------------------------------
# Counted once per person per era: a minister serving under two regimes counts
# in each, which is the convention used throughout the dataset.
ERAS = ["protectorate", "protectorate_end", "monarchy", "bourguiba",
        "ben_ali", "transition", "second_republic", "saied_exception"]
pairs = (appointments[["person_id", "era"]].dropna().drop_duplicates()
         .merge(persons[["person_id", "gender"]], on="person_id"))
known = pairs[pairs.gender.notna()]

rows = []
for era in ERAS:
    block = known[known.era == era]
    if block.empty:
        continue
    rows.append({"era": era, "ministers": len(block),
                 "women": int((block.gender == "female").sum()),
                 "share_women": float((block.gender == "female").mean())})
gender = pd.DataFrame(rows)
print("\nWomen in government, by era")
print(gender.assign(share_women=lambda d: (d.share_women * 100).round(1)
                    .astype(str) + "%").to_string(index=False))
gender.to_csv(OUT / "01_women_by_era.csv", index=False)

print(f"\nWrote 3 tables to {OUT}")
