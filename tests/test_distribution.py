"""Tests for the thing a downloader actually gets.

The pipeline being correct is not the same as the repository being usable. A
clone or a `make bundle` archive has to work with no harvest, no pipeline run,
and no package installs beyond pandas — and the loaders and codebook have to
stay in step with the tables as the schema moves.
"""

import pathlib
import shutil
import subprocess
import sys

import pandas as pd
import pytest

from govtn import config
from govtn.codebook import build_codebook

REPO = config.repo_root()
PROCESSED = config.paths().processed

sys.path.insert(0, str(REPO / "analysis" / "python"))
import load_govtn  # noqa: E402


# --- what a clone ships -----------------------------------------------------

CORE = ["persons", "appointments", "cabinets", "spells", "portfolios",
        "governorates", "eras", "codebook"]


@pytest.mark.parametrize("table", CORE)
def test_core_tables_are_committed(table):
    """A user must not have to run the pipeline to get the data."""
    path = PROCESSED / f"{table}.csv"
    assert path.exists(), f"{path} missing"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path.relative_to(REPO))],
        cwd=REPO, capture_output=True)
    assert tracked.returncode == 0, f"{table}.csv is not tracked by git"


def test_derived_outputs_live_in_their_own_directories():
    """Someone opening data/processed/ should see the tables to load.

    Four core tables buried among eight network exports and three index files
    is the state this guards against.
    """
    loose = {p.stem for p in PROCESSED.glob("*.csv")}
    assert not any(name.startswith("edges_") for name in loose)
    assert not any(name.startswith("network_") for name in loose)
    assert not any(name.startswith("representation_") for name in loose)
    assert (PROCESSED / "networks").is_dir()
    assert (PROCESSED / "indices").is_dir()


# --- the codebook -----------------------------------------------------------

def test_codebook_covers_every_column_of_every_published_table():
    published = pd.read_csv(PROCESSED / "codebook.csv")
    for table in CORE:
        if table == "codebook":
            continue
        frame = pd.read_csv(PROCESSED / f"{table}.csv", low_memory=False, nrows=1)
        documented = set(published[published["table"] == table]["variable"])
        missing = set(frame.columns) - documented
        assert not missing, f"{table} columns absent from codebook.csv: {missing}"


def test_codebook_on_disk_matches_the_tables():
    """Guards the drift that makes a generated codebook worse than none.

    Adding a column and forgetting `make codebook` would leave the loaders
    typing it as character while the docs claim otherwise.
    """
    fresh = build_codebook()
    on_disk = pd.read_csv(PROCESSED / "codebook.csv")
    assert list(fresh["table"] + "." + fresh["variable"]) == \
           list(on_disk["table"] + "." + on_disk["variable"]), \
           "codebook.csv is stale - run `make codebook`"


def test_every_variable_has_a_description():
    on_disk = pd.read_csv(PROCESSED / "codebook.csv")
    undocumented = on_disk[~on_disk["documented"].astype(bool)]
    assert undocumented.empty, (
        "undocumented variables (add them to docs/CODEBOOK.md): "
        + ", ".join(undocumented["table"] + "." + undocumented["variable"])
    )


# --- the Python loader ------------------------------------------------------

def test_python_loader_applies_types_from_the_codebook():
    persons = load_govtn.load("persons")
    assert pd.api.types.is_datetime64_any_dtype(persons["birth_date"])
    assert persons["birth_sahel"].dtype == "boolean"
    assert str(persons["n_appointments"].dtype) == "Int64"


def test_python_loader_preserves_arabic_and_accents():
    """The failure this catches is silent: mojibake still loads and still joins."""
    persons = load_govtn.load("persons")
    arabic = persons["name_ar"].dropna()
    assert not arabic.empty
    assert any("ا" in name for name in arabic), "Arabic letters not preserved"
    assert not any("Ã" in name for name in persons["name"].dropna()), "mojibake"


def test_python_loader_reads_every_declared_table():
    for table in load_govtn.TABLES:
        frame = load_govtn.load(table)
        assert len(frame) > 0, table


def test_identifier_columns_survive_as_strings():
    """Inferred dtypes turn IDs into floats and break joins silently."""
    appointments = load_govtn.load("appointments")
    persons = load_govtn.load("persons")
    # Not `== object`: recent pandas infers StringDtype, which is equally fine.
    # What must never happen is a numeric dtype, which drops leading zeros and
    # turns a missing id into NaN.
    for frame, label in ((appointments, "appointments"), (persons, "persons")):
        assert not pd.api.types.is_numeric_dtype(frame["person_id"]), label
    orphans = set(appointments["person_id"]) - set(persons["person_id"])
    assert not orphans, f"appointments referencing unknown persons: {list(orphans)[:5]}"


def test_panel_joins_without_losing_rows():
    panel = load_govtn.panel()
    appointments = load_govtn.load("appointments")
    assert len(panel) == len(appointments)
    assert "birth_governorate" in panel.columns


def test_loader_finds_the_data_from_a_subdirectory():
    """Users run scripts from wherever they happen to be."""
    found = load_govtn.data_dir(REPO / "analysis" / "python")
    assert found == PROCESSED


# --- the R loader and cross-language agreement ------------------------------

pytestmark_r = pytest.mark.skipif(
    shutil.which("Rscript") is None, reason="Rscript not installed")


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not installed")
def test_r_loader_types_and_encoding_match_python(tmp_path):
    """The R loader is shipped, so it is tested — not assumed to work.

    Base R only: if this ever needs a package, the offline promise in the
    README is broken.
    """
    script = tmp_path / "check.R"
    script.write_text(
        f'source("{REPO}/analysis/R/load_govtn.R")\n'
        f'p <- govtn_load("persons", dir = "{PROCESSED}")\n'
        'cat(nrow(p), ncol(p), class(p$birth_date), class(p$birth_sahel),\n'
        '    sum(p$birth_sahel, na.rm = TRUE),\n'
        '    sum(!is.na(p$name_ar)), sep = "|")\n',
        encoding="utf-8")
    result = subprocess.run(["Rscript", str(script)], capture_output=True,
                            text=True, cwd=REPO)
    assert result.returncode == 0, result.stderr
    rows, cols, date_class, bool_class, sahel, arabic = \
        result.stdout.strip().split("|")

    persons = load_govtn.load("persons")
    assert int(rows) == len(persons)
    assert int(cols) == len(persons.columns)
    assert date_class == "Date"
    assert bool_class == "logical"
    assert int(sahel) == int(persons["birth_sahel"].sum())
    assert int(arabic) == int(persons["name_ar"].notna().sum())


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="Rscript not installed")
def test_r_reproduces_the_published_representation_index():
    """`02_representation_gini.R` recomputes the index and fails if it differs.

    Running it here means the published numbers are checked against an
    independent base-R implementation on every test run.
    """
    result = subprocess.run(
        ["Rscript", str(REPO / "analysis" / "R" / "02_representation_gini.R")],
        capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Reproduced" in result.stdout


def test_python_reproduces_the_published_representation_index():
    result = subprocess.run(
        [sys.executable, str(REPO / "analysis" / "python" / "02_representation_gini.py")],
        capture_output=True, text=True, cwd=REPO)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Reproduced" in result.stdout


# --- citation metadata ------------------------------------------------------

def test_citation_file_is_present_and_parses():
    import yaml
    path = REPO / "CITATION.cff"
    assert path.exists()
    with path.open(encoding="utf-8") as fh:
        meta = yaml.safe_load(fh)
    assert meta["cff-version"]
    assert meta["authors"]
    assert meta["title"]
