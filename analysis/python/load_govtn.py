"""GovMembersTN - loader for Python.

Needs pandas and nothing else. No network access: clone or unzip the
repository and this works offline.

    import sys; sys.path.insert(0, "analysis/python")
    from load_govtn import load_all, describe

    tn = load_all()
    tn["persons"].head()

Column types are not hard-coded here. They come from
`data/processed/codebook.csv`, which is generated from the tables themselves,
so dates parse as datetimes and flags as booleans without this file having to
be kept in step with the schema.

The R loader in `analysis/R/load_govtn.R` follows the same contract, so a
result computed in one language can be checked in the other.
"""

from __future__ import annotations

import pathlib

import pandas as pd

# Table -> subdirectory under data/processed.
TABLES: dict[str, str] = {
    "persons": "",
    "appointments": "",
    "cabinets": "",
    "spells": "",
    "portfolios": "",
    "governorates": "",
    "eras": "",
    "codebook": "",
    "representation_gini": "indices",
    "representation_changes": "indices",
    "representation_by_governorate": "indices",
    "edges_bipartite": "networks",
    "edges_co_membership": "networks",
    "edges_succession": "networks",
    "edges_homophily": "networks",
}


def data_dir(start: str | pathlib.Path | None = None) -> pathlib.Path:
    """Find `data/processed/` by walking up from `start`.

    So the scripts run whether Python was started at the repository root, in
    `analysis/python/`, or in a notebook somewhere in the tree.
    """
    path = pathlib.Path(start or pathlib.Path.cwd()).resolve()
    for candidate in [path, *path.parents]:
        processed = candidate / "data" / "processed"
        if (processed / "persons.csv").exists():
            return processed
    raise FileNotFoundError(
        f"could not find data/processed/persons.csv above {path}. "
        "Run from the repository root, or pass directory= to load()."
    )


def codebook(directory: pathlib.Path | None = None) -> pd.DataFrame:
    directory = directory or data_dir()
    return pd.read_csv(directory / "codebook.csv", encoding="utf-8")


def _path_for(table: str, directory: pathlib.Path) -> pathlib.Path:
    sub = TABLES[table]
    return (directory / sub / f"{table}.csv") if sub else directory / f"{table}.csv"


def load(table: str, directory: pathlib.Path | None = None,
         typed: bool = True) -> pd.DataFrame:
    """One table, with types applied from the codebook."""
    if table not in TABLES:
        raise KeyError(f"unknown table {table!r}; available: {', '.join(TABLES)}")
    directory = directory or data_dir()
    path = _path_for(table, directory)
    if not path.exists():
        raise FileNotFoundError(path)

    # Read as strings first. Left to infer, pandas turns identifiers that look
    # numeric into floats, and a column empty in its first rows into all-NaN
    # float - which then silently fails a merge against the same key elsewhere.
    frame = pd.read_csv(path, encoding="utf-8", dtype=str,
                        keep_default_na=True, na_values=[""], low_memory=False)
    if not typed or table == "codebook":
        return frame

    book = codebook(directory)
    spec = book[book["table"] == table]
    for _, row in spec.iterrows():
        column, kind = row["variable"], row["type"]
        if column not in frame.columns:
            continue
        if kind == "date":
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
        elif kind == "boolean":
            frame[column] = frame[column].map(
                {"True": True, "False": False, "TRUE": True, "FALSE": False}
            ).astype("boolean")
        elif kind == "integer":
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
        elif kind == "numeric":
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def load_all(directory: pathlib.Path | None = None) -> dict[str, pd.DataFrame]:
    directory = directory or data_dir()
    return {name: load(name, directory) for name in TABLES}


def describe(table: str, variable: str | None = None,
             directory: pathlib.Path | None = None) -> pd.DataFrame:
    """What does this column mean? Answered without leaving the session."""
    book = codebook(directory or data_dir())
    rows = book[book["table"] == table]
    if variable is not None:
        rows = rows[rows["variable"] == variable]
    if rows.empty:
        raise KeyError(f"no such table or variable: {table}.{variable}")
    for _, row in rows.iterrows():
        print(f"{row['variable']}  [{row['type']}]  {row['coverage']:.0%} present")
        if isinstance(row["levels"], str) and row["levels"]:
            print(f"  values: {row['levels']}")
        if isinstance(row["description"], str) and row["description"]:
            print(f"  {row['description']}")
        print()
    return rows


def panel(directory: pathlib.Path | None = None) -> pd.DataFrame:
    """One row per appointment, with person and cabinet attributes attached.

    The usual starting point for individual-level analysis.
    """
    directory = directory or data_dir()
    appointments = load("appointments", directory)
    persons = load("persons", directory)
    cabinets = load("cabinets", directory)

    person_cols = [c for c in persons.columns if c not in appointments.columns]
    out = appointments.merge(
        persons[["person_id", *person_cols]], on="person_id", how="left")
    cabinet_cols = [c for c in cabinets.columns if c not in out.columns]
    return out.merge(
        cabinets[["cabinet_id", *cabinet_cols]], on="cabinet_id", how="left")


if __name__ == "__main__":
    tables = load_all()
    for name, frame in tables.items():
        print(f"{name:32s} {len(frame):6,d} rows x {len(frame.columns):3d} cols")
