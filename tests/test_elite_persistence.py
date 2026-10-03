"""The elite-persistence export: the misdated copies, the governments, the parties.

Run with:  PYTHONPATH=src python3 -m pytest tests/test_elite_persistence.py -q
"""

from __future__ import annotations

import csv
from pathlib import Path

from govtn import elite_persistence as ep

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "elite_persistence"


def _rows(name: str) -> list[dict]:
    with (OUT / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _row(cabinet, start, **kw):
    base = {"cabinet_id": cabinet, "start_date": start, "date_precision": "day",
            "date_basis": "row", "spell_id": "", "era": ""}
    base.update(kw)
    return base


def test_misdated_copies_are_recognised_and_nothing_else():
    assert ep.is_misdated(_row("Gouvernement Slaheddine Baccouche II", "1987-11-07"))
    assert ep.is_misdated(_row("Gouvernement Mohamed Salah Mzali", "1980-04-23"))
    assert not ep.is_misdated(_row("Gouvernement Slaheddine Baccouche II", "1952-01-01"))
    assert not ep.is_misdated(_row("Gouvernement Hédi Baccouche I", "1987-11-07"))


def test_no_minister_of_the_1940s_is_counted_in_the_1980s():
    layer = _rows("layer_ministers.csv")
    djellouli = [r for r in layer if r["person_id"] == "Q3125297"]
    assert djellouli and all(r["period"] == "protectorate" for r in djellouli)
    assert all("198" not in r["years_in_office"] for r in djellouli)
    # The Arabic-only second entries are gone; the French ones stay.
    ids = {r["person_id"] for r in layer}
    assert "TN-unknown-115" not in ids and "TN-mohamed-hadjouj" in ids
    assert len(ids) == 871


def test_governments_are_read_from_the_date_and_split_at_the_ruptures():
    assert ep.government_at("2011-01-13")[2] == "TN-10"
    assert ep.government_at("2011-01-17")[2] == "TN-10b"
    assert ep.government_at("2011-01-17")[3] == "Mohamed Ghannouchi"
    assert ep.government_at("2021-07-24")[3] == "Hichem Mechichi"
    assert ep.government_at("2021-08-01")[3] == "Kais Saied"
    assert ep.government_at("1987-10-15")[3] == "Habib Bourguiba"
    assert ep.government_at("1956-01-01") is None
    # A 1 January cabinet date is a year, so the spell decides.
    row = _row("Gouvernement Karoui", "1990-01-01", date_basis="cabinet",
               spell_id="TN-09", era="ben_ali")
    assert ep.government_of(row)[2] == "TN-09"


def test_parties_are_one_name_in_either_script():
    assert ep.party_of("حركة النهضة") == ep.party_of("Ennahdha") == "Ennahda"
    assert ep.party_of("Nidaa Tounes puis Tahya Tounes") == "Nidaa Tounes"
    assert ep.party_of("مستقلة") == ep.party_of("Indépendant") == "Independent"
    assert ep.party_of("") == ""


def test_the_appointments_file_counts_each_person_once_first():
    rows = _rows("layer_minister_appointments.csv")
    firsts = [r for r in rows if r["first_since_independence"] == "True"]
    assert len({r["person_id"] for r in rows}) == len(firsts)
    assert len({(r["person_id"], r["government"]) for r in rows}) == len(rows)
    assert {r["coalition"] for r in rows if r["government"] in ("TN-12", "TN-13")} == {"Troika"}
    assert not any(r["government"] < "TN-01" for r in rows)
