"""Data quality checks.

Writes `data/processed/VALIDATION.md` and returns a non-zero exit code if any
ERROR-level check fails. The distinction matters:

  ERROR   - the table is internally inconsistent (a tenure that ends before it
            begins, a foreign key pointing at nothing). Something is wrong
            with the pipeline; the dataset should not be used as-is.
  WARNING - the table is consistent but incomplete or uncertain (missing birth
            dates, portfolios that the taxonomy could not classify, merges
            accepted on name evidence alone). These are properties of the
            SOURCES, not bugs, and they are what a user needs to know before
            interpreting a result.

Coverage statistics are reported unconditionally, because the most dangerous
failure mode for a dataset like this is not a wrong value but an unnoticed
hole: nobody checks whether the 1960s are half empty before computing a
seventy-year trend.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from typing import Any

import pandas as pd

from . import config

log = logging.getLogger(__name__)


class Report:
    def __init__(self) -> None:
        self.sections: list[tuple[str, str, str]] = []   # (level, title, body)

    def add(self, level: str, title: str, body: str) -> None:
        self.sections.append((level, title, body))

    @property
    def errors(self) -> int:
        return sum(1 for level, _, _ in self.sections if level == "ERROR")

    @property
    def warnings(self) -> int:
        return sum(1 for level, _, _ in self.sections if level == "WARNING")

    def render(self, manifest: dict[str, Any]) -> str:
        lines = [
            "# Data validation report",
            "",
            f"- Generated: `{manifest.get('generated_utc', 'unknown')}`",
            f"- Snapshot date: `{manifest.get('snapshot_date', 'unknown')}`",
            f"- Harvest complete: **{manifest.get('complete', False)}**",
            f"- Errors: **{self.errors}** | Warnings: **{self.warnings}**",
            "",
        ]
        if not manifest.get("complete", False):
            missing = [k for k, v in manifest.get("sources_present", {}).items() if not v]
            lines += [
                "> **This dataset was built from a partial harvest.** Missing sources: "
                + ", ".join(f"`{m}`" for m in missing) + ".",
                "> Counts below describe what was built, not what exists.",
                "",
            ]
        for level, title, body in self.sections:
            marker = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}.get(level, "")
            lines += [f"## {marker} {level}: {title}", "", body, ""]
        return "\n".join(lines)


def _table(frame: pd.DataFrame, limit: int = 15) -> str:
    if frame.empty:
        return "_none_"
    shown = frame.head(limit)
    body = shown.to_markdown(index=False)
    if len(frame) > limit:
        body += f"\n\n_{len(frame) - limit} further rows omitted._"
    return body


# ---------------------------------------------------------------------------

def check_internal_consistency(report: Report, appointments: pd.DataFrame,
                               persons: pd.DataFrame) -> None:
    start = pd.to_datetime(appointments["start_date"], errors="coerce")
    end = pd.to_datetime(appointments["end_date"], errors="coerce")

    reversed_rows = appointments[start.notna() & end.notna() & (end < start)]
    if not reversed_rows.empty:
        report.add("ERROR", "Tenures that end before they begin",
                   _table(reversed_rows[["appointment_id", "person_name",
                                         "raw_title", "start_date", "end_date"]]))

    orphans = appointments[~appointments["person_id"].isin(persons["person_id"])]
    if not orphans.empty:
        report.add("ERROR", "Appointments referencing an unknown person_id",
                   _table(orphans[["appointment_id", "person_id", "person_name"]]))

    duplicate_ids = persons[persons["person_id"].duplicated()]
    if not duplicate_ids.empty:
        report.add("ERROR", "Duplicate person_id in persons.csv",
                   _table(duplicate_ids[["person_id", "name"]]))

    spells = {s["id"] for s in config.cabinets()["spells"]}
    bad_spell = appointments[
        appointments["spell_id"].notna() & ~appointments["spell_id"].isin(spells)
    ]
    if not bad_spell.empty:
        report.add("ERROR", "Appointments referencing an unknown spell_id",
                   _table(bad_spell[["appointment_id", "spell_id"]]))


def check_taxonomy_coverage(report: Report, appointments: pd.DataFrame) -> None:
    """Report titles the portfolio taxonomy could not classify.

    An unclassified title is not a bug in the data, it is a gap in
    config/portfolios.yml - and it is actionable: each one names an alias that
    should be added. Left unreported, they silently pool into `other` and any
    portfolio-level analysis quietly loses those posts.
    """
    unmatched = appointments[appointments["portfolio"] == "other"]
    share = len(unmatched) / max(len(appointments), 1)
    if unmatched.empty:
        report.add("INFO", "Portfolio taxonomy coverage",
                   "Every ministerial title was classified.")
        return

    counts = (
        unmatched["raw_title"].value_counts().rename_axis("raw_title")
        .reset_index(name="n")
    )
    path = config.paths().interim / "unmatched_titles.csv"
    counts.to_csv(path, index=False)
    level = "WARNING" if share > 0.05 else "INFO"
    report.add(
        level, f"Unclassified ministerial titles ({len(unmatched)} rows, {share:.1%})",
        f"Written in full to `{path.relative_to(config.repo_root())}`. "
        "Each distinct title below is an alias that should be added to "
        "`config/portfolios.yml`.\n\n" + _table(counts),
    )


def check_attribute_coverage(report: Report, persons: pd.DataFrame) -> None:
    interesting = [
        "birth_date", "birth_place", "gender", "education", "parties",
        "occupations", "profession_domains", "wikidata_qid",
    ]
    rows = []
    for column in interesting:
        if column not in persons.columns:
            rows.append({"variable": column, "present": 0, "coverage": "0.0%"})
            continue
        present = int(persons[column].notna().sum())
        rows.append({
            "variable": column,
            "present": present,
            "coverage": f"{present / max(len(persons), 1):.1%}",
        })
    frame = pd.DataFrame(rows)
    weak = [r["variable"] for r in rows if float(r["coverage"].rstrip("%")) < 50]
    level = "WARNING" if weak else "INFO"
    body = (
        f"Person-level attribute coverage across {len(persons)} people.\n\n"
        + _table(frame, limit=50)
    )
    if weak:
        body += ("\n\nBelow 50% coverage: " + ", ".join(f"`{w}`" for w in weak)
                 + ". Analyses using these variables are effectively "
                   "conditioned on being well documented, which correlates "
                   "with seniority and with the post-2011 period.")
    report.add(level, "Individual-level attribute coverage", body)


def check_temporal_coverage(report: Report, appointments: pd.DataFrame) -> None:
    """Appointments per decade - the check that catches silent holes."""
    years = pd.to_datetime(appointments["start_date"], errors="coerce").dt.year
    decades = (years // 10 * 10).dropna().astype(int)
    counts = Counter(decades)
    rows = [
        {"decade": f"{decade}s", "appointments": counts.get(decade, 0)}
        for decade in range(1950, 2030, 10)
    ]
    frame = pd.DataFrame(rows)
    empty = [r["decade"] for r in rows if r["appointments"] == 0]
    undated = int(years.isna().sum())
    body = _table(frame, limit=20)
    if undated:
        body += f"\n\n{undated} appointments carry no usable start date."
    if empty:
        body += "\n\nDecades with no appointments at all: " + ", ".join(empty) + "."
    report.add("WARNING" if empty else "INFO", "Temporal coverage by decade", body)


def check_seat_conflicts(report: Report, appointments: pd.DataFrame) -> None:
    """Two different people recorded in one seat at the same time.

    Usually a source disagreement or a failed merge rather than a real
    co-holding, so it is surfaced for manual review rather than resolved
    automatically.
    """
    frame = appointments.dropna(subset=["cabinet_id", "portfolio", "person_id"])
    frame = frame[frame["portfolio"] != "other"]
    grouped = (
        frame.groupby(["cabinet_id", "portfolio"])["person_id"]
        .nunique().reset_index(name="n_holders")
    )
    contested = grouped[grouped["n_holders"] > 1]
    if contested.empty:
        report.add("INFO", "Seat conflicts", "No cabinet-portfolio seat has "
                                             "conflicting holders.")
        return
    report.add(
        "WARNING", f"Cabinet seats with more than one recorded holder ({len(contested)})",
        "Expected where a portfolio changed hands mid-cabinet; a problem where "
        "it reflects a source disagreement or a failed merge. Review before "
        "treating these as co-holdings.\n\n" + _table(contested),
    )


def check_place_coding(report: Report, persons: pd.DataFrame) -> None:
    """Birthplaces that `config/places.yml` could not resolve.

    Like an unclassified portfolio, an unmapped settlement is actionable
    rather than fatal: each one names an entry to add. Unreported, the person
    silently drops out of every regional analysis while still appearing in the
    denominator.
    """
    if "birth_place" not in persons.columns:
        return
    known = persons["birth_place"].notna()
    if "birth_governorate" not in persons.columns:
        return
    has_governorate = persons["birth_governorate"].notna()
    # A birthplace outside Tunisia is coded, not missing: it has a country and
    # legitimately has no governorate. Counting it as unmapped would ask for a
    # `settlements` entry that must never be written, and would hide the real
    # gap behind a permanently non-zero warning.
    if "birth_country" in persons.columns:
        coded_elsewhere = persons["birth_country"].notna()
    else:
        coded_elsewhere = pd.Series(False, index=persons.index)
    unmapped = persons[known & ~has_governorate & ~coded_elsewhere]
    coded = int((known & has_governorate).sum())
    total = int(known.sum())
    body = (
        f"{coded}/{total} recorded birthplaces resolved to a governorate "
        f"({coded / max(total, 1):.1%})."
    )
    if "birth_abroad" in persons.columns:
        abroad = persons[persons["birth_abroad"].fillna(False).astype(bool)]
        country_only = persons[known & ~has_governorate & coded_elsewhere
                               & ~persons["birth_abroad"].fillna(False).astype(bool)]
        if len(abroad) or len(country_only):
            body += (
                f" A further {len(abroad)} were born outside Tunisia and "
                f"{len(country_only)} name the country only; both are coded in "
                "`birth_country` and carry no governorate by design."
            )
    if unmapped.empty:
        report.add("INFO", "Birthplace coding", body)
        return
    counts = (
        unmapped["birth_place"].value_counts().rename_axis("birth_place")
        .reset_index(name="n")
    )
    report.add(
        "WARNING", f"Unmapped birthplaces ({len(counts)} distinct)",
        body + "\n\nAdd each settlement below to the `settlements` map in "
        "`config/places.yml`, or to `foreign_origins` if it lies outside "
        "Tunisia. Until then these people are absent from every regional "
        "analysis while still counting in the denominator.\n\n"
        + _table(counts),
    )


def check_reconciliation(report: Report) -> None:
    path = config.paths().interim / "reconciliation_audit.json"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        audit = json.load(fh)
    name_merges = [m for m in audit["merges"] if m["rule"] == "name_similarity"]
    borderline = sorted(
        (m for m in name_merges if m.get("score") is not None and m["score"] < 0.95),
        key=lambda m: m["score"],
    )
    body = (
        f"{len(audit['merges'])} merges accepted, {len(audit['vetoed'])} vetoed by a "
        f"disqualifier. {len(name_merges)} rest on name similarity alone "
        f"(threshold {audit['threshold']})."
    )
    if borderline:
        frame = pd.DataFrame(borderline)[["left", "right", "score"]]
        body += ("\n\nLowest-scoring name-only merges, which are the ones worth "
                 "eyeballing:\n\n" + _table(frame, limit=20))
    report.add("WARNING" if borderline else "INFO",
               "Entity resolution decisions", body)


# ---------------------------------------------------------------------------

def run() -> int:
    paths = config.paths().ensure()
    appointments = pd.read_csv(paths.processed / "appointments.csv")
    persons = pd.read_csv(paths.processed / "persons.csv")
    manifest_path = paths.processed / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    report = Report()
    check_internal_consistency(report, appointments, persons)
    check_taxonomy_coverage(report, appointments)
    check_attribute_coverage(report, persons)
    check_temporal_coverage(report, appointments)
    check_seat_conflicts(report, appointments)
    check_place_coding(report, persons)
    check_reconciliation(report)

    output = paths.processed / "VALIDATION.md"
    output.write_text(report.render(manifest), encoding="utf-8")
    log.info("wrote %s - %d errors, %d warnings",
             output, report.errors, report.warnings)
    return 1 if report.errors else 0


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
