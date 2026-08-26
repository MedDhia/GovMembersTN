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
