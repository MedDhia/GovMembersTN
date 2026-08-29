"""Tests for the territorial representation index."""

import pandas as pd
import pytest

from govtn.inequality import (
    MIN_MINISTERS,
    UNITS,
    UNREPRESENTATIVE,
    era_comparisons,
    gini_counts,
    gini_from_lorenz,
    governorate_populations,
    governorate_ratios,
    lorenz,
    representation_table,
)

# Four governorates of very unequal size, so weighting is not a no-op.
POPS = {"Big": 8_000_000, "Mid": 1_500_000, "Small": 400_000, "Tiny": 100_000}


def _gini(counts):
    return gini_from_lorenz(lorenz(counts, POPS))


def test_perfect_proportionality_is_zero():
    """The index must be 0 when ministers track population exactly."""
    counts = {"Big": 80, "Mid": 15, "Small": 4, "Tiny": 1}
    assert _gini(counts) == pytest.approx(0.0, abs=1e-9)


def test_everything_from_the_smallest_place_approaches_one():
    """All ministers from the 1%-of-population governorate is the extreme."""
    value = _gini({"Tiny": 50})
    assert value > 0.98
    # The ceiling is 1 - (population share of that governorate), not 1.
    assert value == pytest.approx(1 - POPS["Tiny"] / sum(POPS.values()), abs=1e-9)


def test_index_is_bounded_and_ordered():
    proportional = _gini({"Big": 80, "Mid": 15, "Small": 4, "Tiny": 1})
    skewed = _gini({"Big": 95, "Mid": 5})
    extreme = _gini({"Tiny": 100})
    assert 0 <= proportional < skewed < extreme <= 1


def test_unrepresented_governorates_count_as_zeros():
    """Dropping the governorates that supplied nobody would understate it.

    Those are precisely the cases the measure exists to capture, so a
    governorate absent from the counts must still consume its population share
    along the Lorenz curve.
    """
    with_zeros = _gini({"Big": 50})
    counts_only = {"Big": 50, "Mid": 0, "Small": 0, "Tiny": 0}
    assert _gini(counts_only) == pytest.approx(with_zeros)
    # And it is materially higher than the same counts over a smaller universe.
    just_big = gini_from_lorenz(lorenz({"Big": 50}, {"Big": POPS["Big"]}))
    assert with_zeros > just_big


def test_population_weighting_changes_the_answer():
    """The representation Gini and the count Gini are different quantities.

    Ministers split evenly across four governorates of wildly different size is
    perfectly equal as counts and badly unequal as representation. Reporting
    the count version as though it measured representation is the mistake this
    guards against.
    """
    counts = {"Big": 10, "Mid": 10, "Small": 10, "Tiny": 10}
    assert gini_counts(counts, list(POPS)) == pytest.approx(0.0, abs=1e-9)
    assert _gini(counts) > 0.4


def test_ratio_of_one_is_proportional_representation():
    persons = pd.DataFrame([
        {"person_id": f"P{i}", "birth_governorate": "Tunis"} for i in range(10)
    ])
    appointments = pd.DataFrame([
        {"person_id": f"P{i}", "era": "bourguiba"} for i in range(10)
    ])
    ratios = governorate_ratios(persons, appointments).set_index("governorate")
    # Every minister from Tunis: its ratio is 1 / its population share.
    populations = governorate_populations()
    expected = 1 / (populations["Tunis"] / sum(populations.values()))
    assert ratios.loc["Tunis", "ratio"] == pytest.approx(expected, rel=1e-3)
    assert ratios.loc["Sfax", "ratio"] == 0


def test_thin_eras_are_withheld_with_a_stated_reason(tables):
    """A NaN must never be left for the reader to explain to themselves."""
    table = representation_table(tables["persons"], tables["appointments"], draws=50)
    withheld = table[table["gini_representation"].isna()]
    assert not withheld.empty
    assert withheld["basis"].str.startswith("withheld:").all()
    reported = table[table["gini_representation"].notna()]
    assert (reported["basis"] == "reported").all()
    assert (reported["coded"] >= MIN_MINISTERS).all()


def test_saied_era_is_withheld_for_unrepresentative_coverage(harvested):
    """It clears the count threshold but its coded sample is the wrong people.

    Excluding it must not depend on how many ministers happen to be coded, so
    this asserts the reason, not the count.
    """
    table = representation_table(harvested["persons"],
                                 harvested["appointments"], draws=50)
    row = table[table["era"] == "saied_exception"]
    assert not row.empty
    assert row.iloc[0]["coded"] >= MIN_MINISTERS, "would pass a count-only rule"
    assert pd.isna(row.iloc[0]["gini_representation"])
    assert UNREPRESENTATIVE["saied_exception"] in row.iloc[0]["basis"]


def test_confidence_interval_brackets_the_estimate(harvested):
    """The pivotal interval must contain the point estimate.

    Resampling inflates the Gini, so a naive percentile interval sits above the
    estimate and can exclude it outright. This is the regression guard for that.
    """
    table = representation_table(harvested["persons"],
                                 harvested["appointments"], draws=400)
    reported = table[table["gini_representation"].notna()]
    assert len(reported) >= 3
    for _, row in reported.iterrows():
        assert row["ci_low"] <= row["gini_representation"] <= row["ci_high"], row["era"]


def test_every_governorate_has_a_population():
    """The denominator must be complete, or shares are silently wrong."""
    populations = governorate_populations()
    assert len(populations) == 24
    assert all(p > 50_000 for p in populations.values())
    # Tunisia's 2024 census total, within a rounding margin.
    assert 11_000_000 < sum(populations.values()) < 13_000_000


def test_unknown_partition_is_rejected(tables):
    with pytest.raises(ValueError, match="unknown units"):
        representation_table(tables["persons"], tables["appointments"],
                             units="prefecture", draws=10)


def test_partition_changes_the_level_but_not_the_shape(harvested):
    """The headline guard on this whole measure.

    Splitting Greater Tunis four ways inflates the level - Ariana holds 5.6% of
    the population and supplies no minister, because it did not exist as a
    governorate when these people were born. So the level is only meaningful
    relative to a stated partition, while the ORDERING of eras must survive all
    three or nothing can be claimed about the trend.
    """
    series = {}
    for units in UNITS:
        table = representation_table(harvested["persons"], harvested["appointments"],
                                     units=units, draws=50)
        reported = table[table["gini_representation"].notna()]
        series[units] = list(reported["gini_representation"])
        assert (reported["units"] == units).all()

    lengths = {len(v) for v in series.values()}
    assert len(lengths) == 1, "partitions must report the same eras"

    # Levels differ substantially between partitions...
    assert series["governorate"][-1] > series["region"][-1] + 0.15
    # ...but every partition agrees the protectorate is the most unequal era
    # and that no later era comes close to it.
    for units, values in series.items():
        assert values[0] == max(values), units
        assert values[0] > max(values[1:]) + 0.2, units


def test_era_differences_are_tested_on_the_difference(harvested):
    """Overlapping per-era intervals are not a test of the change."""
    changes = era_comparisons(harvested["persons"],
                              harvested["appointments"], draws=300)
    assert not changes.empty
    for _, row in changes.iterrows():
        assert row["ci_low"] <= row["delta"] <= row["ci_high"], (row["from"], row["to"])
        assert row["significant"] == bool(row["ci_low"] > 0 or row["ci_high"] < 0)


def test_independence_is_the_only_large_equalisation(harvested):
    """A substantive regression guard, checked under every partition.

    The protectorate-to-Bourguiba fall should be large and significant in all
    three; the post-1987 changes should not be significant in any.
    """
    for units in UNITS:
        changes = era_comparisons(harvested["persons"], harvested["appointments"],
                                  units=units, draws=600).set_index(["from", "to"])
        independence = changes.loc[("protectorate", "bourguiba")]
        assert independence["delta"] < -0.2, units
        assert independence["significant"], units

        revolution = changes.loc[("ben_ali", "transition")]
        assert not revolution["significant"], units
