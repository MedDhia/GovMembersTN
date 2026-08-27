"""Representation inequality: how evenly governorates supply ministers.

WHAT IS BEING MEASURED

A count of ministers per governorate is not a measure of representation. Tunis
supplies the largest bloc of ministers in every regime since 1881, but Tunis is
also the largest governorate - part of that bloc is simply population. The
question "is ministerial recruitment territorially unequal?" only has an answer
once the count is set against the population it is drawn from.

So the unit here is the governorate, weighted by its share of the national
population, and its value is ministers per capita. The Lorenz curve plots
cumulative share of population (x) against cumulative share of ministers (y),
governorates ordered from least to best represented. The Gini is the usual
one-minus-twice-the-area-under-the-curve.

  G = 0   every governorate supplies ministers in exact proportion to its
          population - perfect territorial proportionality
  G = 1   every minister comes from one vanishingly small place

This is NOT the Gini of the minister counts themselves. That number is also
reported, as `gini_counts`, because the gap between the two is informative: a
count-Gini can fall while the representation-Gini stays flat, which happens
when ministers redistribute towards governorates that were already populous.
Reporting only the count-Gini would read as equalisation that has not occurred.

THE LEVEL DEPENDS ON THE PARTITION; THE TREND DOES NOT

A Gini over territorial units is only defined relative to those units, and
Tunisia's have moved. Ariana and Ben Arous were carved out of Greater Tunis in
1983 and Manouba in 2000 - after most ministers in this dataset were born, and
after the sources recording their birthplaces as "Tunis" were written. Splitting
the capital four ways therefore concentrates it artificially: Ariana holds 5.6%
of the population and shows zero ministers, while Tunis shows 3.8x its share.

So three partitions are computed, and the difference between them is the point:

  governorate            all 24 current governorates
  greater_tunis_merged   the four capital governorates as one unit
  region                 the seven regions, stable across every boundary change

On the Second Republic these give 0.42, 0.26 and 0.19. Anyone quoting a single
level must say which partition it came from. What survives all three is the
SHAPE of the series, which is what the eras are being compared on.

A second reason to read trends not levels: the denominator is one census
vintage (2024) applied to ministers born across a century, during which the
capital's suburbs grew enormously and the interior shrank in relative terms. A
fixed denominator makes era-to-era movement pure recruitment change, but it
makes any single level a statement about today's population, not the population
a given cohort was drawn from.

WHAT THE INDEX CANNOT SEE

Territorial units are the unit, so within-unit inequality is invisible: a Sfax
that sends only the sons of its merchant families and a Sfax that sends a
cross-section of its population score identically. The index measures
territorial proportionality, which is one component of an egalitarian claim and
not the whole of it.

A minister is counted once per era, in every era in which they held office - the
same convention as the rest of the tables. Only ministers with a coded
birthplace enter, so each era's index is conditional on its own coverage; see
`coverage` in the output and the birthplace caveats in `VALIDATION.md`.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import random

import pandas as pd

from . import config
from .normalize import clean_name

log = logging.getLogger(__name__)

# Below this many coded ministers the index is dominated by which handful of
# people happen to be documented, and is reported as missing rather than as a
# number. This rules out the beylical, end-of-protectorate and monarchy periods.
MIN_MINISTERS = 25

# Eras whose coded sample is unrepresentative for a reason a count threshold
# cannot catch. The post-2021 cabinets clear MIN_MINISTERS on 30 coded
# ministers, but those 30 are almost entirely holdovers: of the 46 people whose
# first ministerial post came after July 2021, 2 have a coded birthplace (4%),
# against 61% of the holdovers serving beside them. An index built on that
# sample would describe the recruitment of previous regimes, which is the
# opposite of what it would appear to say.
UNREPRESENTATIVE = {
    "saied_exception": "newcomers 4% covered; sample is almost all holdovers",
}

ERA_ORDER = [
    "beylical", "protectorate", "protectorate_end", "monarchy", "bourguiba",
    "ben_ali", "transition", "second_republic", "saied_exception",
]


# The four governorates that made up Greater Tunis before the 1983 and 2000
# splits. Sources predating those splits say "Tunis" for all of them.
GREATER_TUNIS = ("Tunis", "Ariana", "Ben Arous", "Manouba")

UNITS = ("governorate", "greater_tunis_merged", "region")


def _unit_map(units: str) -> tuple[dict[str, str], dict[str, int]]:
    """(governorate -> unit, unit -> population) for one partition."""
    cfg = config.load_yaml("places")
    governorates = [g for g in cfg.get("governorates", []) if g.get("population")]
    if units == "governorate":
        mapping = {g["name"]: g["name"] for g in governorates}
    elif units == "greater_tunis_merged":
        mapping = {
            g["name"]: ("Greater Tunis" if g["name"] in GREATER_TUNIS else g["name"])
            for g in governorates
        }
    elif units == "region":
        mapping = {g["name"]: g["region"] for g in governorates}
    else:
        raise ValueError(f"unknown units {units!r}; expected one of {UNITS}")
    populations: dict[str, int] = {}
    for g in governorates:
        unit = mapping[g["name"]]
        populations[unit] = populations.get(unit, 0) + g["population"]
    return mapping, populations


def governorate_populations() -> dict[str, int]:
    """Governorate -> population, from `config/places.yml`."""
    cfg = config.load_yaml("places")
    return {
        g["name"]: g["population"]
        for g in cfg.get("governorates", [])
        if g.get("population")
    }


def lorenz(counts: dict[str, float], populations: dict[str, int]) -> list[tuple[float, float]]:
    """Lorenz points (cumulative population share, cumulative minister share).

    Governorates are ordered by ministers per capita, least represented first,
    and every governorate in `populations` participates - including those that
    supplied no minister at all. Dropping the zeros would understate inequality
    by exactly the governorates that make the point.
    """
    total_pop = sum(populations.values())
    total_min = sum(counts.get(name, 0) for name in populations)
    if not total_pop or not total_min:
        return []
    ordered = sorted(
        populations,
        key=lambda name: counts.get(name, 0) / populations[name],
    )
    points = [(0.0, 0.0)]
    cum_pop = cum_min = 0.0
    for name in ordered:
        cum_pop += populations[name] / total_pop
        cum_min += counts.get(name, 0) / total_min
        points.append((cum_pop, cum_min))
    return points


def gini_from_lorenz(points: list[tuple[float, float]]) -> float | None:
    """Gini as 1 - 2 x (area under the Lorenz curve), by the trapezoid rule."""
    if len(points) < 2:
        return None
    area = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        area += (x1 - x0) * (y0 + y1) / 2
    return 1 - 2 * area


def gini_counts(counts: dict[str, float], universe: list[str]) -> float | None:
    """Gini of the raw counts across governorates, ignoring population.

    Reported alongside the representation Gini so the two cannot be confused.
    Governorates with no minister are included as zeros.
    """
    values = sorted(counts.get(name, 0) for name in universe)
    n = len(values)
    total = sum(values)
    if not n or not total:
        return None
    weighted = sum((2 * i - n + 1) * v for i, v in enumerate(values))
    return weighted / (n * total)


def _bootstrap(names: list[str], populations: dict[str, int], *,
               point: float, draws: int, seed: int) -> tuple[float, float] | None:
    """Bootstrap confidence interval, resampling ministers with replacement.

    The resampling unit is the individual minister: the uncertainty that
    matters is which particular people held office and which of them ended up
    documented, not sampling from some larger frame of ministers.

    The interval is the BASIC (pivotal) one, `2*point - percentile`, not the
    percentile interval. Resampling with replacement adds dispersion to the
    per-governorate count vector - some governorates are drawn more often,
    others fall to zero - and the Gini rises with that dispersion, so the
    bootstrap distribution sits systematically ABOVE the point estimate. The
    percentile interval inherits that bias and can fail to bracket the estimate
    at all; on the Bourguiba era it returned [0.52, 0.66] around a point of
    0.56, with the estimate almost at its floor. Reflecting the percentiles
    through the point estimate corrects the direction.
    """
    if len(names) < MIN_MINISTERS:
        return None
    rng = random.Random(seed)
    estimates = []
    for _ in range(draws):
        counts: dict[str, float] = {}
        for _ in names:
            pick = names[rng.randrange(len(names))]
            counts[pick] = counts.get(pick, 0) + 1
        value = gini_from_lorenz(lorenz(counts, populations))
        if value is not None:
            estimates.append(value)
    if not estimates:
        return None
    estimates.sort()
    lo_pct = estimates[int(0.025 * (len(estimates) - 1))]
    hi_pct = estimates[int(0.975 * (len(estimates) - 1))]
    return 2 * point - hi_pct, 2 * point - lo_pct


def representation_table(persons: pd.DataFrame, appointments: pd.DataFrame, *,
                         units: str = "governorate",
                         draws: int = 2000, seed: int = 20260827) -> pd.DataFrame:
    """One row per era: Gini, its interval, and the coverage it rests on.

    `units` selects the partition - see the module docstring. The level is not
    comparable across partitions; the series within one is.
    """
    mapping, populations = _unit_map(units)
    universe = list(populations)
    canonical = {clean_name(name): mapping[name] for name in mapping}

    pairs = (
        appointments[["person_id", "era"]].dropna().drop_duplicates()
        .merge(persons[["person_id", "birth_governorate"]], on="person_id", how="left")
    )

    rows = []
    for era in ERA_ORDER:
        block = pairs[pairs["era"] == era]
        if block.empty:
            continue
        coded = block[block["birth_governorate"].notna()]
        names = [
            canonical[key] for key in coded["birth_governorate"].map(clean_name)
            if key in canonical
        ]
        counts: dict[str, float] = {}
        for name in names:
            counts[name] = counts.get(name, 0) + 1

        row = {
            "era": era,
            "units": units,
            "ministers": len(block),
            "coded": len(names),
            "coverage": round(len(names) / len(block), 3) if len(block) else None,
            "governorates_represented": len(counts),
        }
        # Why an era is or is not reported travels with the row, so a NaN is
        # never left for the reader to explain to themselves.
        if era in UNREPRESENTATIVE:
            row["basis"] = f"withheld: {UNREPRESENTATIVE[era]}"
        elif len(names) < MIN_MINISTERS:
            row["basis"] = f"withheld: only {len(names)} coded ministers"
        else:
            row["basis"] = "reported"

        if row["basis"] == "reported":
            value = gini_from_lorenz(lorenz(counts, populations))
            interval = (_bootstrap(names, populations, point=value,
                                   draws=draws, seed=seed)
                        if value is not None else None)
            row["gini_representation"] = round(value, 4) if value is not None else None
            row["ci_low"] = round(interval[0], 4) if interval else None
            row["ci_high"] = round(interval[1], 4) if interval else None
            counts_gini = gini_counts(counts, universe)
            row["gini_counts"] = round(counts_gini, 4) if counts_gini is not None else None
        else:
            row["gini_representation"] = None
            row["ci_low"] = row["ci_high"] = row["gini_counts"] = None
        rows.append(row)
    return pd.DataFrame(rows)


def era_comparisons(persons: pd.DataFrame, appointments: pd.DataFrame, *,
                    units: str = "governorate", pairs: list[tuple[str, str]] | None = None,
                    draws: int = 4000, seed: int = 20260827) -> pd.DataFrame:
    """Change in the index between consecutive eras, with a bootstrap interval.

    Overlapping per-era intervals are not a test of the difference - two
    estimates can each carry wide intervals and still differ reliably, or the
    reverse. This resamples both eras jointly and builds the interval on the
    DIFFERENCE, which is the quantity an era-to-era claim actually rests on.
    Same pivotal correction as `_bootstrap`, for the same reason.
    """
    mapping, populations = _unit_map(units)
    canonical = {clean_name(name): mapping[name] for name in mapping}
    linked = (
        appointments[["person_id", "era"]].dropna().drop_duplicates()
        .merge(persons[["person_id", "birth_governorate"]], on="person_id", how="left")
    )

    def units_for(era: str) -> list[str]:
        block = linked[(linked["era"] == era) & linked["birth_governorate"].notna()]
        return [
            canonical[key] for key in block["birth_governorate"].map(clean_name)
            if key in canonical
        ]

    def gini_of(names: list[str]) -> float | None:
        counts: dict[str, float] = {}
        for name in names:
            counts[name] = counts.get(name, 0) + 1
        return gini_from_lorenz(lorenz(counts, populations))

    if pairs is None:
        usable = [e for e in ERA_ORDER
                  if e not in UNREPRESENTATIVE and len(units_for(e)) >= MIN_MINISTERS]
        pairs = list(zip(usable, usable[1:]))

    rng = random.Random(seed)
    rows = []
    for before, after in pairs:
        a_names, b_names = units_for(before), units_for(after)
        if len(a_names) < MIN_MINISTERS or len(b_names) < MIN_MINISTERS:
            continue
        g_a, g_b = gini_of(a_names), gini_of(b_names)
        if g_a is None or g_b is None:
            continue
        observed = g_b - g_a
        deltas = []
        for _ in range(draws):
            ra = [a_names[rng.randrange(len(a_names))] for _ in a_names]
            rb = [b_names[rng.randrange(len(b_names))] for _ in b_names]
            da, db = gini_of(ra), gini_of(rb)
            if da is not None and db is not None:
                deltas.append(db - da)
        deltas.sort()
        lo_pct = deltas[int(0.025 * (len(deltas) - 1))]
        hi_pct = deltas[int(0.975 * (len(deltas) - 1))]
        lo, hi = 2 * observed - hi_pct, 2 * observed - lo_pct
        rows.append({
            "units": units, "from": before, "to": after,
            "gini_from": round(g_a, 4), "gini_to": round(g_b, 4),
            "delta": round(observed, 4),
            "ci_low": round(lo, 4), "ci_high": round(hi, 4),
            "significant": bool(lo > 0 or hi < 0),
        })
    return pd.DataFrame(rows)


def governorate_ratios(persons: pd.DataFrame, appointments: pd.DataFrame,
                       era: str | None = None) -> pd.DataFrame:
    """Per-governorate representation ratio: minister share / population share.

    1.0 is exact proportionality; 2.0 is twice the ministers its population
    would warrant. `era=None` pools every era.
    """
    mapping, populations = _unit_map("governorate")
    canonical = {clean_name(name): name for name in populations}
    pairs = (
        appointments[["person_id", "era"]].dropna().drop_duplicates()
        .merge(persons[["person_id", "birth_governorate"]], on="person_id", how="left")
    )
    if era:
        pairs = pairs[pairs["era"] == era]
    coded = pairs[pairs["birth_governorate"].notna()]
    names = [
        canonical[key] for key in coded["birth_governorate"].map(clean_name)
        if key in canonical
    ]
    total_pop = sum(populations.values())
    rows = []
    for name, population in populations.items():
        n = names.count(name)
        pop_share = population / total_pop
        min_share = n / len(names) if names else 0
        rows.append({
            "governorate": name,
            "ministers": n,
            "population": population,
            "population_share": round(pop_share, 4),
            "minister_share": round(min_share, 4),
            "ratio": round(min_share / pop_share, 3) if pop_share else None,
        })
    return pd.DataFrame(rows).sort_values("ratio", ascending=False).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--draws", type=int, default=2000,
                        help="bootstrap resamples for the confidence interval")
    parser.add_argument("--out", type=pathlib.Path, default=None,
                        help="directory for the CSV output (default: data/processed/indices)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    processed = config.paths().processed
    persons = pd.read_csv(processed / "persons.csv", low_memory=False)
    appointments = pd.read_csv(processed / "appointments.csv", low_memory=False)

    # All three partitions, because the level is not interpretable without one.
    table = pd.concat(
        [representation_table(persons, appointments, units=units, draws=args.draws)
         for units in UNITS],
        ignore_index=True,
    )
    ratios = governorate_ratios(persons, appointments)
    changes = pd.concat(
        [era_comparisons(persons, appointments, units=units, draws=args.draws)
         for units in UNITS],
        ignore_index=True,
    )

    out_dir = args.out or config.paths().indices
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "representation_gini.csv", index=False)
    ratios.to_csv(out_dir / "representation_by_governorate.csv", index=False)
    changes.to_csv(out_dir / "representation_changes.csv", index=False)

    log.info("wrote representation_gini.csv (%d eras x %d partitions)",
             len(table) // len(UNITS), len(UNITS))
    log.info("wrote representation_by_governorate.csv (%d governorates)", len(ratios))
    shown = table[table["gini_representation"].notna()]
    wide = shown.pivot(index="era", columns="units", values="gini_representation")
    wide = wide.reindex([e for e in ERA_ORDER if e in wide.index])
    print(wide.to_string())
    print()
    print(changes[["units", "from", "to", "delta", "ci_low", "ci_high",
                   "significant"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
