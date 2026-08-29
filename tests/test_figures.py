"""The committed figures must stay in step with the committed data.

A figure is the one artefact in this repository a reader cannot check by
eye against the tables, so it is the one most likely to go stale unnoticed:
nothing about a PNG announces that it was rendered three enrichment rounds
ago. These tests do not render anything - they check that every figure the
docs promise is present, and that the numbers a figure was drawn from still
agree with `data/processed/`.
"""
import pathlib

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIGURES = ROOT / "figures"
PROCESSED = ROOT / "data" / "processed"

STEMS = [
    "fig01_coverage_by_decade",
    "fig02_women_share_by_era",
    "fig03_representation_gini",
    "fig04_lorenz_curves",
    "fig05_representation_by_governorate",
    "fig06_cabinet_continuity",
    "fig07_government_size_over_time",
    "fig08_rank_composition_by_era",
    "fig09_survival_in_office",
    "fig10_turnover_and_renewal",
    "fig11_sovereign_portfolio_tenure",
    "fig12_regional_composition_by_era",
    "fig13_region_mixing_matrix",
    "fig14_age_at_first_appointment",
    "fig15_cabinets_served",
    "fig16_top_centrality",
    "fig17_survival_in_office_by_region",
    "fig18_survival_in_government_by_regime",
    "fig19_survival_in_government_by_region",
    "fig20_exit_and_global_shocks",
    "fig21_homophily_channels",
    "fig22_elite_persistence_across_eras",
    "fig23_succession_within_region",
    "fig24_governorate_parity_by_era",
    "fig25_coast_sahel_interior",
    "fig26_seat_switching_and_career",
]


@pytest.mark.parametrize("stem", STEMS)
def test_every_figure_ships_all_three_files(stem):
    """PNG for screen, PDF for LaTeX, CSV as the table view. All committed."""
    for path in (FIGURES / f"{stem}.png", FIGURES / f"{stem}.pdf",
                 FIGURES / "tables" / f"{stem}.csv"):
        assert path.exists(), f"{path.relative_to(ROOT)} is missing"
        assert path.stat().st_size > 0, f"{path.relative_to(ROOT)} is empty"


@pytest.mark.parametrize("stem", STEMS)
def test_figures_readme_documents_every_figure(stem):
    text = (FIGURES / "README.md").read_text(encoding="utf-8")
    assert stem in text, f"figures/README.md does not mention {stem}"


def test_generator_builds_exactly_the_documented_figures():
    """The script's own list is the source of truth; nothing drifts silently."""
    source = (FIGURES / "make_figures.py").read_text(encoding="utf-8")
    for stem in STEMS:
        assert f'"{stem}"' in source, f"make_figures.py no longer builds {stem}"


def test_gini_figure_still_matches_the_published_index():
    """The recompute baked into fig. 3 must still hold for the current data.

    `make_figures` asserts this at render time, but a rendered figure outlives
    the data it was drawn from - this re-checks it from the committed CSV, so
    a rebuild of `data/processed/` that moves the index fails here rather than
    leaving a quietly wrong picture in the repository.
    """
    table = pd.read_csv(FIGURES / "tables" / "fig03_representation_gini.csv")
    published = pd.read_csv(PROCESSED / "indices" / "representation_gini.csv")

    merged = table.merge(published[["era", "units", "gini_representation"]],
                         on=["era", "units"], suffixes=("_fig", "_now"))
    assert len(merged) == len(published), "figure table lost era x partition rows"

    both = merged.dropna(subset=["gini_representation_fig", "gini_representation_now"])
    assert len(both) >= 3, "no reported eras left to check"
    worst = (both["gini_representation_fig"] - both["gini_representation_now"]).abs().max()
    assert worst < 5e-4, (
        f"fig. 3 was drawn from a different index than the one published "
        f"(worst |diff| = {worst:.2e}); re-run `make figures`")

    # Withholding is a claim the figure makes visually - it must still be true.
    fig_withheld = set(table.loc[table["gini_representation"].isna(), "era"])
    now_withheld = set(published.loc[published["gini_representation"].isna(), "era"])
    assert fig_withheld == now_withheld, (
        "the eras the index withholds have changed; fig. 3 shades the old set")


def test_women_figure_matches_the_appointments_table():
    """Fig. 2's denominator is gender-coded ministers, and that moves."""
    table = pd.read_csv(FIGURES / "tables" / "fig02_women_share_by_era.csv")
    persons = pd.read_csv(PROCESSED / "persons.csv", low_memory=False)
    appointments = pd.read_csv(PROCESSED / "appointments.csv", low_memory=False)

    pairs = (appointments[["person_id", "era"]].dropna().drop_duplicates()
             .merge(persons[["person_id", "gender"]], on="person_id", how="left"))
    for _, row in table.iterrows():
        block = pairs[pairs["era"] == row["era"]]
        known = block[block["gender"].notna()]
        assert len(known) == row["ministers_with_known_gender"], (
            f"{row['era']}: figure drawn with {row['ministers_with_known_gender']} "
            f"gender-coded ministers, data now has {len(known)}")
        women = int((known["gender"].str.lower() == "female").sum())
        assert women == row["women"], f"{row['era']}: women count moved"


def test_readme_shows_a_figure_that_exists():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    import re
    embedded = re.findall(r"!\[[^\]]*\]\((figures/[^)]+)\)", readme)
    assert embedded, "README.md no longer shows any figure"
    for rel in embedded:
        assert (ROOT / rel).exists(), f"README embeds {rel}, which does not exist"


def test_no_orphan_figure_files():
    """A renamed figure must not leave its predecessor behind.

    `fig07` was rebuilt from cabinet roster size to people-in-office and
    renamed with it. The old png, pdf and csv would otherwise have sat in the
    repository forever, indistinguishable from a current figure.
    """
    stems = set(STEMS)
    for path in sorted(FIGURES.glob("fig*.*")):
        assert path.stem in stems, f"{path.name} belongs to no current figure"
    for path in sorted((FIGURES / "tables").glob("fig*.csv")):
        assert path.stem in stems, f"tables/{path.name} belongs to no current figure"


def test_mixing_matrix_is_symmetric_and_centred_on_chance():
    """Fig. 13's normalisation is easy to get wrong and the error is invisible.

    Adding a whole edge to both cells of an undirected pair counts every
    cross-region tie twice and every same-region tie once. The matrix still
    looks plausible - but the diagonal is halved, and the figure then claims
    ministers from the same region avoid each other. Half an edge each way is
    the fix; these are the two properties that catch the regression.
    """
    table = pd.read_csv(FIGURES / "tables" / "fig13_region_mixing_matrix.csv")
    regions = table["region"].tolist()
    matrix = table.set_index("region")[regions]

    for a in regions:
        for b in regions:
            assert abs(matrix.loc[a, b] - matrix.loc[b, a]) < 5e-3, (
                f"mixing matrix is not symmetric at ({a}, {b})")

    diagonal = [matrix.loc[r, r] for r in regions]
    assert min(diagonal) > 0.7, (
        f"same-region ratios bottom out at {min(diagonal)} - the diagonal is "
        "being under-counted relative to the off-diagonal cells")
    assert max(diagonal) < 1.4, f"diagonal implausibly high: {max(diagonal)}"


def test_duration_figures_exclude_cabinet_inherited_dates():
    """`build` says an inherited cabinet span is an upper bound, not a tenure.

    Fig. 9's medians are only meaningful under that filter, so this checks the
    counts behind it match a filtered recount rather than the raw table.
    """
    table = pd.read_csv(FIGURES / "tables" / "fig09_survival_in_office.csv")
    app = pd.read_csv(PROCESSED / "appointments.csv", low_memory=False)
    eligible = app[
        app["date_basis"].isin(["statement", "row"])
        & ~app["end_date_unreliable"].fillna(False)
        & app["tenure_days"].notna()
    ]
    for _, row in table.iterrows():
        n = int((eligible["era"] == row["era"]).sum())
        assert n == row["n"], (
            f"{row['era']}: figure drawn with n={row['n']}, filtered data has "
            f"{n}; re-run `make figures`")
        assert 0 < row["median_years"] < 25, row["era"]


@pytest.mark.parametrize("stem", [
    "fig09_survival_in_office",
    "fig17_survival_in_office_by_region",
    "fig18_survival_in_government_by_regime",
    "fig19_survival_in_government_by_region",
])
def test_survival_medians_are_within_the_observed_window(stem):
    """A Kaplan-Meier median outside the plotted x-range is a silent lie.

    The curve is drawn to a fixed axis; if a group's median falls beyond it the
    reader sees a curve that never crosses 0.5 and no median marker, with
    nothing saying why.
    """
    table = pd.read_csv(FIGURES / "tables" / f"{stem}.csv")
    limit = 12 if "in_office" in stem else 30
    assert len(table) >= 2, f"{stem} needs at least two groups to compare"
    for _, row in table.iterrows():
        assert row["n"] >= 40, f"{stem}: {row.iloc[0]} drawn on n={row['n']}"
        assert row["censored"] <= row["n"]
        median = row["median_years"]
        assert pd.notna(median), f"{stem}: no median for {row.iloc[0]}"
        assert 0 < median < limit, (
            f"{stem}: median {median} for {row.iloc[0]} falls outside the "
            f"plotted 0-{limit}y window")


def test_shock_figure_still_shows_the_reshuffle_calendar():
    """Fig. 20's whole claim is that exits track cabinet formation, not shocks.

    It states specific numbers in its caption. If a rebuild moved them the
    caption would be quietly wrong, which on a figure whose point is "do not
    read an effect here" is worse than usual.
    """
    table = pd.read_csv(FIGURES / "tables" / "fig20_exit_and_global_shocks.csv")
    formed = table[table["cabinet_formed"]]["exit_rate"]
    other = table[~table["cabinet_formed"]]["exit_rate"]
    assert len(formed) >= 10 and len(other) >= 30
    assert formed.median() > 4 * other.median(), (
        "formation years no longer dominate the exit series; fig. 20's caption "
        f"claims 0.55 against 0.06, data now has {formed.median():.2f} against "
        f"{other.median():.2f}")
    # The four shocks the caption calls ordinary must still be ordinary.
    for year in (1973, 1979, 2008, 2022):
        rate = table.loc[table["year"] == year, "exit_rate"].iloc[0]
        assert rate <= other.quantile(0.95), (
            f"{year} is no longer an ordinary year ({rate:.2f}); fig. 20's "
            "caption names it as one")


def test_succession_chance_baseline_is_a_probability():
    """Fig. 23 is only readable because of its chance baseline."""
    table = pd.read_csv(FIGURES / "tables" / "fig23_succession_within_region.csv")
    for _, row in table.iterrows():
        assert 0 < row["chance"] < 1, row["era"]
        assert 0 <= row["same_region"] <= 1, row["era"]
        assert row["handovers"] >= 25, row["era"]
