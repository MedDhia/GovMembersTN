"""The codebook must document every column that the pipeline emits.

Without this test the codebook silently rots the first time a column is added.
"""
import re
import pathlib

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODEBOOK = ROOT / "docs" / "CODEBOOK.md"
PROCESSED = ROOT / "data" / "processed"

# Table -> subdirectory under data/processed, mirroring how they are published.
TABLES = {
    "persons": "", "appointments": "", "cabinets": "", "spells": "",
    "portfolios": "", "governorates": "", "eras": "",
    "edges_bipartite": "networks", "edges_co_membership": "networks",
    "edges_succession": "networks", "edges_homophily": "networks",
}


def table_path(name: str) -> pathlib.Path:
    sub = TABLES[name]
    return (PROCESSED / sub / f"{name}.csv") if sub else PROCESSED / f"{name}.csv"


def documented_columns() -> set[str]:
    text = CODEBOOK.read_text(encoding="utf-8")
    # Column names appear as `backticked` cells at the start of a table row,
    # possibly several comma-separated in one cell.
    names: set[str] = set()
    for row in re.findall(r"^\|\s*([^|]+?)\s*\|", text, flags=re.MULTILINE):
        for token in re.findall(r"`([a-z0-9_]+)`", row):
            names.add(token)
    return names


@pytest.mark.parametrize("table", TABLES)
def test_every_column_is_documented(table):
    path = table_path(table)
    if not path.exists():
        pytest.skip(f"{table}.csv not built")
    columns = set(pd.read_csv(path).columns)
    missing = sorted(columns - documented_columns())
    assert not missing, f"undocumented columns in {table}.csv: {missing}"


def test_codebook_warns_about_date_precision():
    # The single most consequential caveat in this dataset.
    text = CODEBOOK.read_text(encoding="utf-8")
    assert "date_precision" in text
    assert "censored" in text.lower()


def test_readme_prose_figures_match_the_data():
    """The percentages in prose, not just the numbers in the table.

    The coverage sentence and the portfolio count had each drifted twice while
    the headline table stayed correct, because only the table was under test.
    A reader has no way to tell a stale percentage from a current one.
    """
    import re
    import pandas as pd

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    persons = pd.read_csv(table_path("persons"), low_memory=False)
    appointments = pd.read_csv(table_path("appointments"), low_memory=False)

    def pct(series):
        return round(series.notna().mean() * 100)

    # "Wikidata QID 68%, occupation 66%, gender 67%, ..."
    coverage_claims = dict(
        (label.strip().lower(), int(value))
        for label, value in re.findall(
            r"([A-Za-z][A-Za-z ]+?)\s+(\d{1,3})%", readme)
    )
    expected = {
        "wikidata qid": pct(persons["wikidata_qid"]),
        "occupation": pct(persons["occupations"]),
        "gender": pct(persons["gender"]),
        "arabic name": pct(persons["name_ar"]),
        "birth date": pct(persons["birth_date"]),
        "birthplace": pct(persons["birth_place"]),
        "education": pct(persons["education"]),
        "party": pct(persons["parties"]),
        "career flags": pct(persons["career_flags"]),
    }
    for label, value in expected.items():
        assert label in coverage_claims, f"README no longer states coverage for {label}"
        assert coverage_claims[label] == value, (
            f"README says {coverage_claims[label]}% for {label}, data has {value}%")

    # Day-precise start dates, and dates that describe the person not the cabinet.
    day = round((appointments["date_precision"] == "day").mean() * 100)
    personal = round(appointments["date_basis"].isin(["statement", "row"]).mean() * 100)
    assert f"{day}% of\nappointments have a day-precise start date" in readme \
        or f"{day}% of appointments have a day-precise start date" in readme, \
        f"README day-precision figure is stale; data has {day}%"
    assert f"{personal}% of appointments carry a date describing the person" in readme, \
        f"README date_basis figure is stale; data has {personal}%"

    # The portfolio count appears in two places and was wrong in both.
    portfolios = len(pd.read_csv(table_path("portfolios")))
    assert f"{portfolios} canonical portfolios" in readme
    assert f"{portfolios} harmonised portfolios" in readme

    # The pre/post-independence split in the opening paragraph.
    years = pd.to_datetime(appointments["start_date"], errors="coerce").dt.year
    post = int((years >= 1956).sum())
    assert f"{post:,} of {len(appointments):,} appointments" in readme, \
        f"README opening figure is stale; data has {post:,} post-1956"


def test_readme_names_only_files_that_exist():
    """Every path the README points at must be real.

    Directory reorganisations move files faster than prose gets updated.
    """
    import re
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\((?!https?:)([^)]+)\)", readme)
    missing = [link for link in links if not (ROOT / link).exists()]
    assert not missing, f"README links to missing files: {missing}"

    # Modules and configs named in the layout block.
    named = re.findall(r"^\s{2}([a-z_]+\.(?:py|yml))\s{2,}", readme, re.M)
    for name in set(named):
        found = list(ROOT.rglob(name))
        assert found, f"README layout names {name}, which does not exist"


def test_readme_make_targets_exist():
    """A README that documents a target the Makefile lost is worse than silence."""
    import re
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^make ([a-z]+)", readme, re.M))
    assert targets, "no make targets documented in README.md"
    for target in sorted(targets):
        assert re.search(rf"^{target}:", makefile, re.M), \
            f"README documents `make {target}`, which the Makefile does not define"


def test_readme_headline_figures_match_the_data():
    """The README's summary table must not drift from the tables it describes.

    It had gone stale by three enrichment rounds - advertising 902 people and
    2,979 appointments against an actual 884 and 3,151 - which is exactly the
    kind of error a reader has no way to detect.
    """
    import re
    import pandas as pd

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    claimed = {
        re.sub(r"[^a-z ]", "", label.lower()).strip(): int(value.replace(",", ""))
        for value, label in re.findall(r"\|\s*\*\*([\d,]+)\*\*\s*\|\s*([^|]+?)\s*\|", readme)
    }
    assert claimed, "no headline figures found in README.md"

    def rows(name):
        return len(pd.read_csv(table_path(name)))

    appointments = pd.read_csv(table_path("appointments"), low_memory=False)

    actual = {
        "people who held a post in a tunisian government": rows("persons"),
        "appointments  one row per person  cabinet  portfolio": rows("appointments"),
        # These two rows sat unguarded while the five around them were checked,
        # and the cabinet count duly drifted to 57 against an actual 56. Every
        # bolded row in the table is covered now.
        "cabinets  across  government spells": rows("cabinets"),
        "appointments carrying a journal officiel citation":
            int(appointments["jort_citation"].notna().sum()),
        "comembership ties weighted by days of overlapping service":
            rows("edges_co_membership"),
        "succession ties directed within portfolio": rows("edges_succession"),
        "homophily ties  shared university party or birth governorate":
            rows("edges_homophily"),
    }
    for label, expected in actual.items():
        assert label in claimed, f"README no longer states: {label}"
        assert claimed[label] == expected, (
            f"README says {claimed[label]} for {label!r}, data has {expected}"
        )

    # Nothing bolded is left out: a new row added without a check here is a
    # row free to drift, which is the failure this test exists to prevent.
    assert set(claimed) == set(actual), (
        f"headline rows with no check: {sorted(set(claimed) - set(actual))}")


def test_readme_inline_counts_match_the_data():
    """The numbers written into the prose of the headline table, not just the
    bolded ones.

    The cabinet row carries two counts - the bolded cabinet total and the spell
    count inside the label - and only the first is in the bold-cell regex above.
    The year range is the same kind of claim: cheap to state, easy to leave
    behind when the spine gains a government.
    """
    import re
    import pandas as pd

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cabinets = pd.read_csv(table_path("cabinets"))
    spells = len(pd.read_csv(table_path("spells")))

    assert f"across {spells} government spells" in readme, \
        f"README spell count is stale; data has {spells}"

    first = pd.to_datetime(cabinets["start_date"], errors="coerce").dt.year.min()
    last = pd.to_datetime(cabinets["end_date"], errors="coerce").dt.year.max()
    assert f"{int(first)}–{int(last)}" in readme, \
        f"README cabinet year range is stale; data spans {int(first)}–{int(last)}"


def test_readme_test_count_matches_the_suite():
    """The layout block advertises the size of the suite, and it had gone stale.

    It read 250 when the suite had grown well past it. Counting `def test_`
    statically is exact and cheap; the parametrised case count is checked
    loosely, since a new `parametrize` legitimately moves it.
    """
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    functions = sum(
        len(re.findall(r"^def test_", path.read_text(encoding="utf-8"), re.M))
        for path in sorted((ROOT / "tests").glob("test_*.py")))

    match = re.search(r"(\d+) test functions, (\d+) cases", readme)
    assert match, "README no longer states the suite size in its layout block"
    claimed_functions, claimed_cases = int(match.group(1)), int(match.group(2))
    assert claimed_functions == functions, (
        f"README says {claimed_functions} test functions, tests/ defines "
        f"{functions}")
    assert claimed_cases >= claimed_functions, (
        "cases cannot be fewer than the functions that generate them")
