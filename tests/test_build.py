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


def test_pipeline_produces_a_valid_dataset(tables):
    """Structural invariants, not row counts.

    Counts depend on how much has been harvested, so asserting them pins the
    test to one harvest state and breaks the moment a source is added.
    """
    assert set(tables) == {"persons", "appointments", "cabinets", "spells", "portfolios"}
    appointments = tables["appointments"]
    # The curated spine alone guarantees at least the 23 head-of-government rows.
    assert len(appointments) >= 23
    assert appointments["person_id"].notna().all()
    # Era is assigned from the start date, so it is null exactly where the
    # start date is unknown - a Wikidata statement with no P580 qualifier.
    # It must never be null for a row that HAS a date.
    dated = appointments[appointments["start_date"].notna()]
    assert dated["era"].notna().all(), (
        "a dated appointment fell outside every era interval"
    )
    assert appointments["appointment_id"].is_unique
    # Every appointment resolves to a person, and every person is referenced.
    assert set(appointments["person_id"]) <= set(tables["persons"]["person_id"])
    assert tables["persons"]["person_id"].is_unique


def test_every_head_of_government_appears_exactly_once_per_spell(tables):
    spine_rows = tables["appointments"].query("source == 'spine'")
    assert len(spine_rows) == len(tables["spells"])
    assert spine_rows["spell_id"].is_unique


def test_incumbent_tenure_is_censored_at_the_snapshot(tables):
    from govtn import config
    incumbents = tables["appointments"].query("is_incumbent and start_date.notna()")
    assert len(incumbents) >= 1
    # An open tenure must get a finite, positive duration, not NaN or infinity.
    assert (incumbents["tenure_days"] > 0).all()
    censor = config.snapshot_date()
    import pandas as pd
    starts = pd.to_datetime(incumbents["start_date"])
    expected = (pd.Timestamp(censor) - starts).dt.days
    assert (incumbents["tenure_days"] - expected).abs().max() <= 1


def test_career_sequence_is_numbered_per_person(tables):
    appointments = tables["appointments"]
    person_id = appointments.loc[
        appointments["person_name"] == "Habib Bourguiba", "person_id"
    ].iloc[0]
    bourguiba = appointments.query("person_id == @person_id")
    # He heads two spells, so at minimum two appointments, numbered from 1.
    assert len(bourguiba) >= 2
    assert sorted(bourguiba["appointment_seq"]) == list(range(1, len(bourguiba) + 1))
    assert bourguiba["is_first_appointment"].sum() == 1


def test_manifest_flags_a_partial_harvest(tables):
    import json
    from govtn import config
    manifest = json.loads((config.paths().processed / "MANIFEST.json").read_text())
    assert "snapshot_date" in manifest
    assert "sources_present" in manifest
    assert manifest["complete"] == all(manifest["sources_present"].values())


def test_biographical_seed_populates_the_person_frame(tables):
    persons = tables["persons"]
    bourguiba = persons.loc[persons["name"] == "Habib Bourguiba"].iloc[0]
    # Whether this comes from the seed or from Wikidata, it must stay
    # day-precise: a full ISO timestamp must not degrade to 1 January.
    assert bourguiba["birth_date"] == "1903-08-03"
    assert bourguiba["birth_date_precision"] == "day"
    assert bourguiba["birth_place"] == "Monastir"
    assert bourguiba["wikidata_qid"] == "Q643348"
    # The seed's QID becomes the person_id, so the row joins straight to a
    # later Wikidata harvest instead of relying on name matching.
    assert bourguiba["person_id"] == "Q643348"


def test_display_name_prefers_the_canonical_form(tables):
    # "Longest variant" alone picks alternate transliterations.
    persons = tables["persons"]
    names = set(persons["name"])
    assert "Béji Caïd Essebsi" in names and "Béji Caïd Es-Sebsi" not in names
    assert "Ali Larayedh" in names and "Ali Laarayedh" not in names
    assert "Hédi Nouira" in names


def test_birthplaces_are_coded_to_governorate_and_region(tables):
    persons = tables["persons"].set_index("name")
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


def test_reduced_date_precision_is_reported_not_hidden(tables):
    """Precision must be recorded for every date, and never overstate a source.

    This deliberately avoids naming a person: which people have day-precise
    birth dates changes as sources improve, so pinning the test to one person
    makes it fail when the data gets BETTER.
    """
    persons = tables["persons"]
    dated = persons[persons["birth_date"].notna()]
    assert len(dated) > 0
    assert dated["birth_date_precision"].notna().all()
    assert set(dated["birth_date_precision"]) <= {"day", "month", "year"}
    # Precision must be derived from the source string rather than guessed
    # from the value: someone genuinely born on 1 January is day-precise, and
    # a year-only source is not. That mapping is unit-tested in
    # tests/test_normalize.py; here we only require it to be carried through.
    assert (dated["birth_date_precision"] == "day").sum() > 0


def test_empty_harvest_file_does_not_count_as_a_present_source(tmp_path):
    """A stage that fails after discovery still writes an empty JSON file.

    Counting that as "present" would report the harvest as complete.

    NOTE: this exercises the predicate directly against tmp_path. An earlier
    version wrote a real source filename into data/interim/ and unlinked it in
    a finally block - which deleted an actual harvest. Tests must never write
    into the live data directory.
    """
    from govtn.build import _contributed_factory

    contributed = _contributed_factory(tmp_path)

    (tmp_path / "empty.json").write_text("[]", encoding="utf-8")
    (tmp_path / "populated.json").write_text('[{"a": 1}]', encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    assert contributed("populated") is True
    assert contributed("empty") is False, "an empty harvest is not a contribution"
    assert contributed("broken") is False
    assert contributed("absent") is False
