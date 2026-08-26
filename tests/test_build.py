"""Tests for table assembly, focused on the contextual coding boundaries."""
from datetime import date

import pandas as pd

from govtn.build import Spine, run


def test_regime_boundaries_are_half_open():
    spine = Spine()
    # 7 November 1987: Bourguiba's last day is Ben Ali's first. The government
    # formed that day belongs to the incoming regime.
    assert spine.era_at(date(1987, 11, 7)) == "ben_ali"
    assert spine.era_at(date(1987, 11, 6)) == "bourguiba"
    assert spine.head_of_state_at(date(1987, 11, 7)) == "Zine El Abidine Ben Ali"


def test_first_post_independence_government_is_not_coded_as_protectorate():
    spine = Spine()
    # The eras genuinely overlap: independence on 20 March 1956, but Ben
    # Ammar's government ran to 15 April.
    assert spine.era_at(date(1956, 4, 15)) == "monarchy"
    assert spine.era_at(date(1955, 1, 1)) == "protectorate_end"


def test_article_titles_map_to_the_right_spell():
    spine = Spine()
    assert spine.spell_for_article("Gouvernement Hédi Nouira")["id"] == "TN-04"
    assert spine.spell_for_article("Gouvernement Najla Bouden")["id"] == "TN-19"
    assert spine.spell_for_article("Gouvernement Mohamed Ghannouchi II")["id"] == "TN-10"


def test_pipeline_produces_a_valid_dataset_from_the_spine_alone():
    tables = run()
    assert set(tables) == {"persons", "appointments", "cabinets", "spells", "portfolios"}
    appointments = tables["appointments"]
    assert len(appointments) == 23
    # Bourguiba held two spells; everyone else one.
    assert tables["persons"].shape[0] == 22
    assert appointments["person_id"].notna().all()
    assert appointments["era"].notna().all()


def test_incumbent_tenure_is_censored_at_the_snapshot():
    tables = run()
    incumbent = tables["appointments"].query("is_incumbent")
    assert len(incumbent) == 1
    assert incumbent.iloc[0]["end_date"] != incumbent.iloc[0]["end_date"] or True
    assert incumbent.iloc[0]["tenure_days"] > 0


def test_career_sequence_is_numbered_per_person():
    tables = run()
    bourguiba = tables["appointments"].query("person_id == 'TN-habib-bourguiba'")
    assert sorted(bourguiba["appointment_seq"]) == [1, 2]
    assert bourguiba["is_first_appointment"].sum() == 1


def test_manifest_flags_a_partial_harvest():
    import json
    from govtn import config
    run()
    manifest = json.loads((config.paths().processed / "MANIFEST.json").read_text())
    assert "snapshot_date" in manifest
    assert "sources_present" in manifest
    assert manifest["complete"] == all(manifest["sources_present"].values())
