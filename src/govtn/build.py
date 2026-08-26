"""Assemble the analysis tables from harvested sources.

Output (data/processed/):

    spells.csv        one row per government spell (the curated spine)
    cabinets.csv      one row per numbered cabinet, resolved from Wikipedia
    persons.csv       one row per person - the individual-level analysis frame
    appointments.csv  one row per person-cabinet-portfolio spell - the long
                      format that everything else is derived from
    portfolios.csv    the harmonised portfolio reference table
    MANIFEST.json     snapshot date, row counts, source provenance

The appointments table is the core. It is deliberately LONG rather than wide:
one row per office held, so a minister who moves between portfolios produces
several rows and can be analysed as a career sequence.

The pipeline runs with whatever sources are present. With no harvest at all it
still emits a valid, non-empty dataset built from the curated spine (heads of
government and their tenures); each harvested source then adds rows and
columns. `MANIFEST.json` always records which sources contributed, so a table
is never mistaken for being more complete than it is.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from . import config
from .normalize import clean_name, parse_date, parse_title
from .reconcile import Reconciler, SourceRecord

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_interim(name: str) -> Any:
    path = config.paths().interim / name
    if not path.exists():
        log.warning("no %s - continuing without it", path.name)
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _iso(value: Any) -> str | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, date):
        return value.isoformat()
    parsed = parse_date(str(value))
    return parsed.value.isoformat() if parsed.value else None


def _year(value: Any) -> int | None:
    iso = _iso(value)
    return int(iso[:4]) if iso else None


# ---------------------------------------------------------------------------
# Contextual lookups from the curated spine
# ---------------------------------------------------------------------------

class Spine:
    """The curated government spine, with date-based lookups."""

    def __init__(self) -> None:
        cfg = config.cabinets()
        self.spells = cfg["spells"]
        self.eras = cfg["eras"]
        self.heads_of_state = cfg["heads_of_state"]
        self.never_invested = {
            clean_name(p["name"]) for p in cfg.get("designated_never_invested", [])
        }
        self.censor = config.snapshot_date()

    def _covering(self, records: list[dict], when: date | None) -> dict | None:
        """First record whose interval contains `when`, treated as HALF-OPEN.

        Regime periods are [start, end): a period ends on the day the next one
        begins. With inclusive ends, every government formed on a transition
        date is assigned to the outgoing regime - Hédi Baccouche, appointed on
        7 November 1987, would be coded under Bourguiba rather than Ben Ali,
        and Bourguiba's own first government would fall under the protectorate.
        The eras also genuinely overlap (independence on 20 March 1956, but
        Ben Ammar's government ran to 15 April), so first-match-wins on
        half-open intervals is what resolves the boundary correctly.
        """
        if when is None:
            return None
        for record in records:
            start = _iso(record.get("start"))
            end = _iso(record.get("end"))
            if start and when < date.fromisoformat(start):
                continue
            if end and when >= date.fromisoformat(end):
                continue
            return record
        return None

    def era_at(self, when: date | None) -> str | None:
        era = self._covering(self.eras, when)
        return era["id"] if era else None

    def head_of_state_at(self, when: date | None) -> str | None:
        head = self._covering(self.heads_of_state, when)
        return head["name"] if head else None

    def spell_at(self, when: date | None) -> dict | None:
        return self._covering(self.spells, when)

    def spell_for_article(self, article: str) -> dict | None:
        """Map a Wikipedia cabinet article to a spell by its head's name.

        Article titles are of the form "Gouvernement <head>[ <numeral>]", so
        the head's surname is the discriminator. Longest surname first, so
        "Gouvernement Bourguiba II" is not claimed by a shorter match.
        """
        normalised = clean_name(article)
        best, best_len = None, 0
        for spell in self.spells:
            for token in clean_name(spell["head"]).split():
                if len(token) < 4:
                    continue
                if token in normalised and len(token) > best_len:
                    best, best_len = spell, len(token)
        return best


# ---------------------------------------------------------------------------
# Record collection
# ---------------------------------------------------------------------------

def collect_records(spine: Spine) -> tuple[list[SourceRecord], list[dict]]:
    """Build source records for reconciliation and raw appointment rows."""
    records: list[SourceRecord] = []
    appointments: list[dict] = []
    counter = 0

    def new_id(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}{counter:05d}"

    # -- (a) the curated spine: heads of government -------------------------
    # Always present, so the dataset is never empty and always carries the one
    # series that is verified end to end.
    for spell in spine.spells:
        record_id = new_id("s")
        start = _iso(spell["start"])
        end = _iso(spell.get("end"))
        records.append(SourceRecord(
            record_id=record_id, source="spine", name=spell["head"],
            cabinet=spell["id"], portfolio="head_of_government",
        ))
        appointments.append({
            "record_id": record_id,
            "cabinet_id": spell["id"],
            "spell_id": spell["id"],
            "cabinet_article": None,
            "raw_title": spell["head_role"].replace("_", " ").title(),
            "person_name": spell["head"],
            "person_wikilink": spell.get("wikipedia_fr"),
            "portfolio": "head_of_government",
            "rank": "head_of_government",
            "is_interim": False,
            "start_date": start,
            "end_date": end,
            "date_precision": "day",
            "source": "spine",
            "source_ref": "config/cabinets.yml",
            "confidence": spell.get("confidence", "high"),
        })

    # -- (b) Wikipedia cabinet rosters --------------------------------------
    for cabinet in _load_interim("wikipedia_cabinets.json") or []:
        article = cabinet["article"]
        spell = spine.spell_for_article(article)
        infobox = cabinet.get("infobox") or {}
        cab_start = infobox.get("start_date") or (spell or {}).get("start")
        cab_end = infobox.get("end_date") or (spell or {}).get("end")
        for member in cabinet["members"]:
            if clean_name(member["person_name"]) in spine.never_invested:
                continue                       # designated but never took office
            parsed = parse_title(member["raw_title"])
            record_id = new_id("w")
            records.append(SourceRecord(
                record_id=record_id, source="wikipedia",
                name=member["person_name"],
                wikilink=member.get("person_wikilink"),
                cabinet=article, portfolio=parsed.portfolio,
            ))
            member_start = _iso(member.get("date_note")) or _iso(cab_start)
            appointments.append({
                "record_id": record_id,
                "cabinet_id": article,
                "spell_id": (spell or {}).get("id"),
                "cabinet_article": article,
                "raw_title": member["raw_title"],
                "person_name": member["person_name"],
                "person_wikilink": member.get("person_wikilink"),
                "portfolio": parsed.portfolio,
                "rank": parsed.rank,
                "is_interim": parsed.is_interim,
                "start_date": member_start,
                "end_date": _iso(cab_end),
                "date_precision": parse_date(member.get("date_note") or str(cab_start)).precision,
                "source": f"wikipedia:{cabinet.get('lang', 'fr')}",
                "source_ref": f"https://{cabinet.get('lang','fr')}.wikipedia.org/wiki/{article.replace(' ', '_')}",
                "confidence": "medium",
                "party_raw": member.get("party"),
            })

    # -- (c) Wikidata officeholding statements ------------------------------
    for row in _load_interim("wikidata_officeholders.json") or []:
        record_id = new_id("d")
        start = _iso(row.get("start"))
        end = _iso(row.get("end"))
        parsed = parse_title(row.get("positionLabel") or "")
        spell = spine.spell_at(date.fromisoformat(start)) if start else None
        records.append(SourceRecord(
            record_id=record_id, source="wikidata",
            name=row.get("personLabel") or "",
            qid=row.get("person_qid"),
            portfolio=parsed.portfolio,
        ))
        appointments.append({
            "record_id": record_id,
            "cabinet_id": (spell or {}).get("id"),
            "spell_id": (spell or {}).get("id"),
            "cabinet_article": None,
            "raw_title": row.get("positionLabel"),
            "person_name": row.get("personLabel"),
            "person_wikilink": None,
            "portfolio": parsed.portfolio,
            "rank": parsed.rank,
            "is_interim": parsed.is_interim,
            "start_date": start,
            "end_date": end,
            "date_precision": "day" if start else "unknown",
            "source": "wikidata",
            "source_ref": row.get("statement") or row.get("person"),
            "confidence": "high" if start else "low",
            "replaces": row.get("replacesLabel"),
            "replaced_by": row.get("replacedByLabel"),
        })

    # -- (d) Leaders biographies (person attributes only, no appointments) ---
    for bio in _load_interim("leaders_biographies.json") or []:
        name = _name_from_leaders(bio)
        if not name:
            continue
        records.append(SourceRecord(
            record_id=new_id("l"), source="leaders", name=name,
            birth_year=_year(bio.get("birth_date")), payload=bio,
        ))

    return records, appointments


def _name_from_leaders(bio: dict) -> str | None:
    """Recover the subject's name from a Leaders headline.

    Headlines are formulaic ("Biographie de X", "Qui est X", "X : Who's Who",
    "X - Ministre de ..."), so the decorations are stripped rather than parsed.
    """
    import re
    title = bio.get("article_title") or ""
    title = re.split(r"\s[-–—:]\s", title)[0]
    title = re.sub(
        r"^\s*(biographie\s+de|qui\s+est|portrait\s+de|le\s+parcours\s+de|who'?s\s+who)\s*",
        "", title, flags=re.IGNORECASE,
    )
    title = re.sub(r"[,:].*$", "", title).strip(" ?«»\"'")
    return title if 3 <= len(title) <= 60 else None


# ---------------------------------------------------------------------------
# Table construction
# ---------------------------------------------------------------------------

def build_persons(
    mapping: dict[str, str],
    records: list[SourceRecord],
    appointments: pd.DataFrame,
) -> pd.DataFrame:
    """One row per person: the individual-level analysis frame."""
    wikidata_persons = {
        row["person_qid"]: row for row in (_load_interim("wikidata_persons.json") or [])
        if row.get("person_qid")
    }
    by_person: dict[str, list[SourceRecord]] = {}
    for record in records:
        by_person.setdefault(mapping[record.record_id], []).append(record)

    rows = []
    for person_id, members in by_person.items():
        names = [m.name for m in members if m.name]
        wd = wikidata_persons.get(person_id, {})
        leaders = next((m.payload for m in members if m.source == "leaders" and m.payload), {})

        birth = _iso(wd.get("birth")) or leaders.get("birth_date")
        death = _iso(wd.get("death"))
        row = {
            "person_id": person_id,
            "wikidata_qid": person_id if person_id.startswith("Q") else None,
            "name": max(names, key=len) if names else None,
            "name_variants": "|".join(sorted({clean_name(n) for n in names})),
            "name_ar": wd.get("personLabelAr"),
            "name_en": wd.get("personLabelEn"),
            "gender": wd.get("genderLabel"),
            "birth_date": birth,
            "birth_year": _year(birth),
            "death_date": death,
            "death_year": _year(death),
            "birth_place": wd.get("birthPlaceLabel") or leaders.get("birth_place"),
            "birth_region": wd.get("birthRegionLabel"),
            "birth_place_qid": wd.get("birth_place_qid"),
            "citizenship": wd.get("countryLabel"),
            "education": _merge_multi(
                wd.get("education"), "|".join(leaders.get("education_institutions", []))
            ),
            "degrees": _merge_multi(
                wd.get("degrees"),
                "|".join(d.get("degree", "") for d in leaders.get("degrees", [])),
            ),
            "academic_fields": wd.get("fields"),
            "occupations": wd.get("occupations"),
            "profession_domains": "|".join(leaders.get("profession_domains", [])) or None,
            "parties": wd.get("parties"),
            "party_qids": wd.get("partyQids"),
            "religion": wd.get("religions"),
            "awards": wd.get("awards"),
            "wikipedia_fr": wd.get("frwiki"),
            "wikipedia_ar": wd.get("arwiki"),
            "wikipedia_en": wd.get("enwiki"),
            "leaders_url": leaders.get("source_url"),
            "sources": "|".join(sorted({m.source for m in members})),
        }
        rows.append(row)

    persons = pd.DataFrame(rows)
    return _attach_career_variables(persons, appointments)


def _merge_multi(*values: str | None) -> str | None:
    parts: list[str] = []
    for value in values:
        if value:
            parts.extend(p.strip() for p in str(value).split("|") if p.strip())
    seen, out = set(), []
    for part in parts:
        key = clean_name(part)
        if key and key not in seen:
            seen.add(key)
            out.append(part)
    return "|".join(out) or None


def _attach_career_variables(persons: pd.DataFrame, appointments: pd.DataFrame) -> pd.DataFrame:
    """Career-level derived variables, computed from the appointments table."""
    if appointments.empty:
        return persons

    appts = appointments.copy()
    appts["start_dt"] = pd.to_datetime(appts["start_date"], errors="coerce")
    appts["end_dt"] = pd.to_datetime(appts["end_date"], errors="coerce")

    ranks = {r["canonical"]: r["level"] for r in config.portfolios()["ranks"]}
    power = {p["canonical"]: p.get("power_rank") for p in config.portfolios()["portfolios"]}
    appts["rank_level"] = appts["rank"].map(ranks).fillna(99)
    appts["is_sovereign"] = appts["portfolio"].map(power).eq("sovereign")

    grouped = appts.groupby("person_id")
    career = pd.DataFrame({
        "n_appointments": grouped.size(),
        "n_cabinets": grouped["cabinet_id"].nunique(),
        "n_portfolios": grouped["portfolio"].nunique(),
        "first_appointment": grouped["start_dt"].min(),
        "last_appointment_end": grouped["end_dt"].max(),
        "total_tenure_days": grouped["tenure_days"].sum(),
        "max_rank_level": grouped["rank_level"].min(),      # lower level = higher rank
        "ever_sovereign_portfolio": grouped["is_sovereign"].any(),
        "ever_head_of_government": grouped["portfolio"].apply(
            lambda s: bool((s == "head_of_government").any())
        ),
        "portfolios_held": grouped["portfolio"].apply(lambda s: "|".join(sorted(set(s)))),
        "eras_served": grouped["era"].apply(lambda s: "|".join(sorted(set(s.dropna())))),
    }).reset_index()

    merged = persons.merge(career, on="person_id", how="left")
    merged["first_appointment"] = merged["first_appointment"].dt.date.astype("string")
    merged["last_appointment_end"] = merged["last_appointment_end"].dt.date.astype("string")

    # Age at entry into government - a standard elite-renewal measure.
    birth = pd.to_datetime(merged["birth_date"], errors="coerce")
    first = pd.to_datetime(merged["first_appointment"], errors="coerce")
    merged["age_at_first_appointment"] = ((first - birth).dt.days / 365.25).round(1)
    merged["career_span_years"] = (
        (pd.to_datetime(merged["last_appointment_end"], errors="coerce") - first).dt.days / 365.25
    ).round(1)
    return merged


def build_appointments(mapping: dict[str, str], raw: list[dict], spine: Spine) -> pd.DataFrame:
    """One row per office held, with contextual and duration variables."""
    frame = pd.DataFrame(raw)
    if frame.empty:
        return frame
    frame["person_id"] = frame["record_id"].map(mapping)

    censor = spine.censor
    labels = {p["canonical"]: p for p in config.portfolios()["portfolios"]}
    ranks = {r["canonical"]: r["level"] for r in config.portfolios()["ranks"]}

    def _as_date(value) -> date | None:
        # pandas represents a missing value as NaN, which is truthy; testing
        # these with `if value:` silently passes NaN to date.fromisoformat.
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, date):
            return value
        text = str(value).strip()
        return date.fromisoformat(text[:10]) if text and text.lower() != "nan" else None

    def duration(row) -> float | None:
        start = _as_date(row["start_date"])
        if start is None:
            return None
        end = _as_date(row["end_date"]) or censor
        return (end - start).days

    frame["tenure_days"] = frame.apply(duration, axis=1)
    frame["is_incumbent"] = frame["end_date"].isna()
    frame["portfolio_label"] = frame["portfolio"].map(
        lambda p: (labels.get(p) or {}).get("label_en")
    )
    frame["portfolio_power_rank"] = frame["portfolio"].map(
        lambda p: (labels.get(p) or {}).get("power_rank")
    )
    frame["rank_level"] = frame["rank"].map(ranks)

    starts = pd.to_datetime(frame["start_date"], errors="coerce")
    frame["era"] = [spine.era_at(d.date() if pd.notna(d) else None) for d in starts]
    frame["president"] = [spine.head_of_state_at(d.date() if pd.notna(d) else None) for d in starts]
    frame["head_of_government"] = frame["spell_id"].map(
        {s["id"]: s["head"] for s in spine.spells}
    )
    frame["start_year"] = starts.dt.year

    # Career sequence position, which is what makes this usable for career-path
    # analysis rather than just cross-sectional description.
    frame = frame.sort_values(["person_id", "start_date"], na_position="last")
    frame["appointment_seq"] = frame.groupby("person_id").cumcount() + 1
    frame["is_first_appointment"] = frame["appointment_seq"] == 1

    frame.insert(0, "appointment_id", [f"A{i:05d}" for i in range(1, len(frame) + 1)])
    return frame


def build_cabinets(
    appointments: pd.DataFrame, persons: pd.DataFrame, spine: Spine
) -> pd.DataFrame:
    """One row per cabinet actually observed, with size and composition."""
    spells = pd.DataFrame(spine.spells).rename(
        columns={"id": "spell_id", "head": "head_of_government"}
    )
    if appointments.empty:
        return spells

    gender = persons.set_index("person_id")["gender"] if "gender" in persons else None
    frame = appointments.copy()
    frame["is_woman"] = (
        frame["person_id"].map(gender).astype("string").str.lower().eq("female")
        if gender is not None else False
    )

    grouped = frame.groupby("cabinet_id")
    cabinets = pd.DataFrame({
        "n_members": grouped["person_id"].nunique(),
        "n_appointments": grouped.size(),
        "n_women": grouped.apply(
            lambda g: g.loc[g["is_woman"], "person_id"].nunique(), include_groups=False
        ),
        "n_sovereign_posts": grouped.apply(
            lambda g: int((g["portfolio_power_rank"] == "sovereign").sum()),
            include_groups=False,
        ),
        "start_date": grouped["start_date"].min(),
        "end_date": grouped["end_date"].max(),
        "spell_id": grouped["spell_id"].first(),
        "era": grouped["era"].first(),
        "president": grouped["president"].first(),
    }).reset_index()
    cabinets["share_women"] = (cabinets["n_women"] / cabinets["n_members"]).round(3)
    cabinets = cabinets.merge(
        spells[["spell_id", "head_of_government", "head_role", "confidence"]],
        on="spell_id", how="left",
    )
    return cabinets


# ---------------------------------------------------------------------------

def run(*, out_dir=None) -> dict[str, pd.DataFrame]:
    paths = config.paths().ensure()
    out_dir = out_dir or paths.processed
    spine = Spine()

    records, raw_appointments = collect_records(spine)
    reconciler = Reconciler()
    reconciler.add_all(records)
    mapping = reconciler.resolve()
    reconciler.write_audit()

    appointments = build_appointments(mapping, raw_appointments, spine)
    persons = build_persons(mapping, records, appointments)
    cabinets = build_cabinets(appointments, persons, spine)

    portfolios = pd.DataFrame(config.portfolios()["portfolios"]).drop(columns=["aliases"])
    spells = pd.DataFrame(spine.spells)

    tables = {
        "persons": persons,
        "appointments": appointments,
        "cabinets": cabinets,
        "spells": spells,
        "portfolios": portfolios,
    }
    for name, frame in tables.items():
        path = out_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        log.info("wrote %-14s %5d rows x %2d cols", path.name, len(frame), frame.shape[1])

    _write_manifest(out_dir, tables, spine)
    return tables


def _write_manifest(out_dir, tables, spine: Spine) -> None:
    sources_present = {
        name: (config.paths().interim / f"{name}.json").exists()
        for name in ("wikidata_persons", "wikidata_officeholders",
                     "wikipedia_cabinets", "leaders_biographies")
    }
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_date": spine.censor.isoformat(),
        "sources_present": sources_present,
        "complete": all(sources_present.values()),
        "tables": {
            name: {"rows": len(frame), "columns": list(frame.columns)}
            for name, frame in tables.items()
        },
    }
    with (out_dir / "MANIFEST.json").open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    if not manifest["complete"]:
        missing = [k for k, v in sources_present.items() if not v]
        log.warning(
            "BUILT FROM A PARTIAL HARVEST - missing: %s. "
            "The tables are valid but under-populated; see MANIFEST.json.",
            ", ".join(missing),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(out_dir=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
