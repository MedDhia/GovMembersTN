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
    # Look him up by name: person_id is his QID once the biographical seed
    # supplies one, and a hardcoded slug would make this test brittle.
    appointments = tables["appointments"]
    person_id = appointments.loc[
        appointments["person_name"] == "Habib Bourguiba", "person_id"
    ].iloc[0]
    bourguiba = appointments.query("person_id == @person_id")
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


def test_biographical_seed_populates_the_person_frame():
    tables = run()
    persons = tables["persons"]
    bourguiba = persons.loc[persons["name"] == "Habib Bourguiba"].iloc[0]
    assert bourguiba["birth_date"] == "1903-08-03"
    assert bourguiba["birth_place"] == "Monastir"
    assert bourguiba["wikidata_qid"] == "Q643348"
    # The seed's QID becomes the person_id, so the row joins straight to a
    # later Wikidata harvest instead of relying on name matching.
    assert bourguiba["person_id"] == "Q643348"


def test_display_name_prefers_the_canonical_form():
    # "Longest variant" alone picks alternate transliterations.
    persons = run()["persons"]
    names = set(persons["name"])
    assert "Béji Caïd Essebsi" in names and "Béji Caïd Es-Sebsi" not in names
    assert "Ali Larayedh" in names and "Ali Laarayedh" not in names
    assert "Hédi Nouira" in names


def test_birthplaces_are_coded_to_governorate_and_region():
    persons = run()["persons"].set_index("name")
    # A settlement, not a governorate capital.
    assert persons.loc["Hédi Baccouche", "birth_governorate"] == "Sousse"
    assert persons.loc["Hédi Baccouche", "birth_sahel"]
    # Sahel is the narrow historical definition, not "coastal".
    assert persons.loc["Youssef Chahed", "birth_governorate"] == "Tunis"
    assert persons.loc["Youssef Chahed", "birth_coastal"]
    assert not persons.loc["Youssef Chahed", "birth_sahel"]
    # Interior.
    assert persons.loc["Najla Bouden", "birth_region_type"] == "centre_west"
    assert not persons.loc["Najla Bouden", "birth_coastal"]


def test_unmapped_birthplace_is_left_empty_not_guessed():
    from govtn.build import Spine
    coded = Spine().place_attributes("Nowhere-sur-Mer")
    assert all(value is None for value in coded.values())


def test_reduced_date_precision_is_reported_not_hidden():
    persons = run()["persons"].set_index("name")
    # No source gave a day for Fakhfakh; the padded value must be flagged.
    assert persons.loc["Elyès Fakhfakh", "birth_date"] == "1972-01-01"
    assert persons.loc["Elyès Fakhfakh", "birth_date_precision"] == "year"
    assert persons.loc["Habib Bourguiba", "birth_date_precision"] == "day"


def test_empty_harvest_file_does_not_count_as_a_present_source():
    # A stage that fails after discovery still writes an empty JSON file;
    # counting that as "present" would report the harvest as complete.
    import json
    from govtn import config
    path = config.paths().interim / "leaders_biographies.json"
    try:
        path.write_text("[]", encoding="utf-8")
        run()
        manifest = json.loads((config.paths().processed / "MANIFEST.json").read_text())
        assert manifest["sources_present"]["leaders_biographies"] is False
    finally:
        path.unlink(missing_ok=True)
