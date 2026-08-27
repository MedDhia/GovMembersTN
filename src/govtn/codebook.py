"""Machine-readable data dictionary for the published tables.

WHY A SECOND CODEBOOK

`docs/CODEBOOK.md` is written for a person deciding whether a variable means
what they need. This one is written for a machine, and for the moment three
weeks later when someone has `persons.csv` open in R and wants to know what
`date_basis` is without leaving the console.

It is GENERATED from the tables themselves, so it cannot drift out of date
about which columns exist, how full they are, or what values a categorical
takes. Prose descriptions come from `docs/CODEBOOK.md`: the markdown remains
the single place a human writes a definition, and a missing one is reported
rather than silently left blank.
"""

from __future__ import annotations

import argparse
import logging
import re

import pandas as pd

from . import config

log = logging.getLogger(__name__)

# Tables a user is expected to load directly, in the order they matter.
CORE_TABLES = ["persons", "appointments", "cabinets", "spells", "portfolios",
               "governorates", "eras"]
INDEX_TABLES = ["representation_gini", "representation_changes",
                "representation_by_governorate"]
NETWORK_TABLES = ["edges_bipartite", "edges_co_membership",
                  "edges_succession", "edges_homophily"]

# A column with at most this many distinct non-null values is treated as
# categorical and its levels are enumerated. Above it, listing every value
# would be a data dump rather than a dictionary.
MAX_LEVELS = 12

# The markdown is not one table shape but several: `| name | type | description |`
# for the core tables, `| name | description |` for the network and index ones,
# and rows that define two columns at once (`| `start_date`, `end_date` | ... |`).
# Rather than one regex per shape, take every backticked identifier in the FIRST
# cell as a variable name and the LAST cell as its description. Matching only
# the three-column single-name form left 71 variables looking undocumented,
# `appointments.start_date` among them, with the definition sitting right there.
_NAME = re.compile(r"`([a-z][a-z0-9_]*)`")
_DECLARED = re.compile(r"^(string|int|integer|float|numeric|bool|boolean|date|list\[[a-z]+\])$")


def markdown_descriptions() -> dict[str, tuple[str, str]]:
    """Variable -> (declared type, prose description) from docs/CODEBOOK.md.

    The markdown uses `| \\`name\\` | type | description |` rows. Where a name
    appears in more than one table its first description wins; the shared
    columns (`person_id`, `era`) mean the same thing everywhere by design.
    """
    path = config.repo_root() / "docs" / "CODEBOOK.md"
    if not path.exists():
        return {}
    found: dict[str, tuple[str, str]] = {}

    def record(name: str, declared: str, description: str) -> None:
        if not name or name in found:
            return
        # Strip markdown emphasis so the value reads as plain text in a console.
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", description)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text).strip()
        found[name] = (declared.strip(), text)

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        # The first cell must be nothing but backticked names and separators,
        # or this is a prose table that happens to mention a variable.
        head = cells[0]
        names = _NAME.findall(head)
        if not names or re.sub(r"`[^`]*`|[,\s/]", "", head):
            continue
        declared = cells[1] if len(cells) > 2 and _DECLARED.match(cells[1]) else ""
        description = cells[-1]
        for name in names:
            record(name, declared, description)
    return found


def _kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "numeric"
    non_null = series.dropna()
    if non_null.empty:
        return "empty"
    # Dates are stored as ISO strings; detect them so the loaders can be told
    # which columns to parse rather than guessing per column at read time.
    sample = non_null.astype(str).head(200)
    if (sample.str.match(r"^\d{4}-\d{2}-\d{2}$").mean() > 0.9):
        return "date"
    if pd.api.types.is_bool_dtype(non_null.infer_objects()):
        return "boolean"
    return "string"


def describe_table(name: str, frame: pd.DataFrame,
                   descriptions: dict[str, tuple[str, str]]) -> list[dict]:
    rows = []
    for column in frame.columns:
        series = frame[column]
        present = int(series.notna().sum())
        kind = _kind(series)
        declared, description = descriptions.get(column, ("", ""))

        levels = ""
        if kind in {"string", "boolean"}:
            distinct = series.dropna().unique()
            if 0 < len(distinct) <= MAX_LEVELS:
                levels = " | ".join(sorted(str(v) for v in distinct))

        example = ""
        non_null = series.dropna()
        if not non_null.empty and not levels:
            example = str(non_null.iloc[0])[:60]

        rows.append({
            "table": name,
            "variable": column,
            "type": kind,
            "n_present": present,
            "n_missing": int(len(frame) - present),
            "coverage": round(present / len(frame), 3) if len(frame) else 0.0,
            "n_distinct": int(series.nunique(dropna=True)),
            "levels": levels,
            "example": example,
            "description": description or "",
            "documented": bool(description),
        })
    return rows


def build_codebook() -> pd.DataFrame:
    paths = config.paths()
    descriptions = markdown_descriptions()
    sources = (
        [(n, paths.processed / f"{n}.csv") for n in CORE_TABLES]
        + [(n, paths.indices / f"{n}.csv") for n in INDEX_TABLES]
        + [(n, paths.networks / f"{n}.csv") for n in NETWORK_TABLES]
    )
    rows: list[dict] = []
    for name, path in sources:
        if not path.exists():
            log.warning("%s not found - skipping", path.name)
            continue
        frame = pd.read_csv(path, low_memory=False)
        rows.extend(describe_table(name, frame, descriptions))
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero if any variable lacks a description")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    codebook = build_codebook()
    out = config.paths().processed / "codebook.csv"
    codebook.to_csv(out, index=False)

    undocumented = codebook[~codebook["documented"]]
    log.info("wrote codebook.csv - %d variables across %d tables",
             len(codebook), codebook["table"].nunique())
    if not undocumented.empty:
        log.warning("%d variables have no description in docs/CODEBOOK.md:",
                    len(undocumented))
        for _, row in undocumented.iterrows():
            log.warning("  %s.%s", row["table"], row["variable"])
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
