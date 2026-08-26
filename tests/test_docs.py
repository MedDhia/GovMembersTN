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

TABLES = [
    "persons", "appointments", "cabinets", "spells", "portfolios",
    "edges_bipartite", "edges_co_membership", "edges_succession",
    "edges_homophily",
]


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
    path = PROCESSED / f"{table}.csv"
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
        return len(pd.read_csv(PROCESSED / f"{name}.csv"))

    actual = {
        "people who held a post in a tunisian government": rows("persons"),
        "appointments  one row per person  cabinet  portfolio": rows("appointments"),
        "comembership ties weighted by days of overlapping service":
            rows("edges_co_membership"),
        "succession ties directed within portfolio": rows("edges_succession"),
        "homophily ties  shared university party or birth region":
            rows("edges_homophily"),
    }
    for label, expected in actual.items():
        assert label in claimed, f"README no longer states: {label}"
        assert claimed[label] == expected, (
            f"README says {claimed[label]} for {label!r}, data has {expected}"
        )
