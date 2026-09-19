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
    # The five analysis tables, plus the two reference tables that publish the
    # YAML coding decisions as CSV for users without a YAML parser.
    assert set(tables) == {"persons", "appointments", "cabinets", "spells",
                           "portfolios", "governorates", "eras"}
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


def test_foreign_birth_is_coded_rather_than_left_missing():
    """A birth outside Tunisia is a finding, not a gap in the settlement map.

    The beylical-era mamluk administrators were born in Circassia, Georgia and
    the Caucasus. Coding them as unmapped would drop them from regional
    analysis while leaving them in the denominator, and would invite someone to
    "fix" it by inventing a governorate for Paris.
    """
    from govtn.build import Spine
    spine = Spine()
    paris = spine.place_attributes("Paris")
    assert paris["birth_country"] == "France"
    assert paris["birth_abroad"] is True
    assert paris["birth_governorate"] is None
    assert paris["birth_region_type"] is None

    # A polity named as of the time of birth, not a modern successor state.
    assert spine.place_attributes("Circassie")["birth_country"] == "Circassia"

    # The country alone: the country is known, the governorate genuinely is not.
    country_only = spine.place_attributes("Tunisie")
    assert country_only["birth_country"] == "Tunisia"
    assert country_only["birth_abroad"] is False
    assert country_only["birth_governorate"] is None

    tunisian = spine.place_attributes("Sousse")
    assert tunisian["birth_country"] == "Tunisia"
    assert tunisian["birth_abroad"] is False


def test_birthplace_spelling_variants_resolve_to_one_governorate():
    """Sources disagree about the article and the apostrophe.

    Wikidata writes "La Manouba" and "M'saken" where the settlement map says
    "Manouba" and "Msaken". Both spellings must land on the same governorate
    without needing an entry each.
    """
    from govtn.build import Spine
    spine = Spine()
    assert spine.place_attributes("La Manouba")["birth_governorate"] == "Manouba"
    assert spine.place_attributes("Manouba")["birth_governorate"] == "Manouba"
    for spelling in ("M'saken", "Msaken", "M saken"):
        assert spine.place_attributes(spelling)["birth_governorate"] == "Sousse"


def test_birthplace_governorates_come_from_the_qid_not_the_label(tables):
    """Several Tunisian settlement names collide across governorates.

    Matching birthplaces by label puts El Guettar in Kairouan, El Ksar and
    El Mida in Gabès and Ezzahra in Tataouine, because each name is borne by
    more than one place. The map was built from the containment chain of the
    QID that each person's P19 statement actually points at, and these four
    are the regression guard for that.
    """
    from govtn.build import Spine
    spine = Spine()
    expected = {
        "El Guettar": "Gafsa",
        "El Ksar": "Gafsa",
        "El Mida": "Nabeul",
        "Ezzahra": "Ben Arous",
    }
    for place, governorate in expected.items():
        assert spine.place_attributes(place)["birth_governorate"] == governorate


def test_every_recorded_birthplace_is_coded_somehow(harvested):
    """No birthplace should be silently uninterpretable.

    Each one must resolve to a governorate, to a foreign country, or to
    Tunisia-without-a-governorate. Anything else is a person who quietly
    vanishes from regional analysis.
    """
    persons = harvested["persons"]
    known = persons[persons["birth_place"].notna()]
    assert len(known) > 400
    uncoded = known[known["birth_governorate"].isna() & known["birth_country"].isna()]
    assert uncoded.empty, sorted(uncoded["birth_place"].unique())
    # A governorate always implies the country; the converse does not hold.
    with_governorate = known[known["birth_governorate"].notna()]
    assert (with_governorate["birth_country"] == "Tunisia").all()
    assert not with_governorate["birth_abroad"].any()


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


def test_build_refuses_to_replace_a_more_complete_dataset(tmp_path):
    """A clone ships data/processed/ but not the harvested payloads.

    Running `make build` there rebuilds from the curated spine alone, and
    before this guard it silently replaced a 3151-row dataset with 23 rows -
    which made the published data look fabricated.
    """
    import json
    import pytest
    from govtn.build import _would_regress

    (tmp_path / "MANIFEST.json").write_text(json.dumps({
        "sources_present": {"wikidata_persons": True, "wikipedia_cabinets": True,
                            "jort_decrees": False}
    }), encoding="utf-8")

    # A build with none of those sources would lose two of them.
    lost = _would_regress(tmp_path, {"wikidata_persons": False,
                                     "wikipedia_cabinets": False,
                                     "jort_decrees": False})
    assert lost == ["wikidata_persons", "wikipedia_cabinets"]

    # A build with the same sources loses nothing and must be allowed.
    assert _would_regress(tmp_path, {"wikidata_persons": True,
                                     "wikipedia_cabinets": True,
                                     "jort_decrees": False}) == []

    # Gaining a source is not a regression either.
    assert _would_regress(tmp_path, {"wikidata_persons": True,
                                     "wikipedia_cabinets": True,
                                     "jort_decrees": True}) == []


def test_regression_guard_is_silent_on_a_first_build(tmp_path):
    from govtn.build import _would_regress
    assert _would_regress(tmp_path, {"wikidata_persons": False}) == []


# --- Journal Officiel matching ---------------------------------------------

def _jort_fixture(tmp_path, decrees):
    """Write a decree store and point the build's interim loader at it."""
    import json
    interim = tmp_path / "interim"
    interim.mkdir(parents=True, exist_ok=True)
    (interim / "jort_decrees.json").write_text(
        json.dumps({"decrees": decrees, "truncated": []}, ensure_ascii=False),
        encoding="utf-8")
    return interim


def test_a_decree_two_people_could_claim_is_not_attached_to_either(monkeypatch):
    """Mohamed Mzali and Mohamed Salah Mzali are different men.

    Containment scores them 0.9 - one name's tokens are a subset of the
    other's - so the gazette's "Mohamed MZALI" fits both. Date proximity
    cannot separate them: they are two people, not two guesses. Unless the
    decree names an office that only one of them held, it is evidence about
    neither.
    """
    from govtn import build

    decree = {
        "citation": "JORT 1980, N°028, p. 2 (fr)", "year": 1980, "issue": "028",
        "page": 2, "lang": "fr", "kind": "nomination", "portfolio_hint": None,
        "holder": "Mohamed MZALI", "office": "Premier Ministre",
        "effective": None, "published": "1980-04-24", "snippet": "",
        "query": "", "url": "https://jort.tn/x",
    }
    monkeypatch.setattr(build, "_load_interim",
                        lambda name: {"decrees": [decree]} if "jort" in name else None)

    appointments = pd.DataFrame([
        {"appointment_id": "A1", "person_id": "P-mzali",
         "person_name": "Mohamed Mzali", "portfolio": "education",
         "start_date": "1980-04-24"},
        {"appointment_id": "A2", "person_id": "P-salah-mzali",
         "person_name": "Mohamed Salah Mzali", "portfolio": "education",
         "start_date": "1980-04-24"},
    ])
    out = build.attach_jort_citations(appointments.copy())
    assert out["jort_citation"].isna().all(), (
        "a decree matching two distinct people was attached anyway")


def test_the_office_named_in_a_decree_breaks_the_tie(monkeypatch):
    """Ambiguity by name is resolved by evidence, not abandoned.

    The same two Mzalis, but now the decree names a portfolio only one of them
    holds in the row being matched. That is an assertion about identity, and
    it is allowed to decide.
    """
    from govtn import build

    decree = {
        "citation": "JORT 1980, N°028, p. 2 (fr)", "year": 1980, "issue": "028",
        "page": 2, "lang": "fr", "kind": "nomination", "portfolio_hint": None,
        "holder": "Mohamed MZALI", "office": "Premier Ministre",
        "effective": None, "published": "1980-04-24", "snippet": "",
        "query": "", "url": "https://jort.tn/x",
    }
    monkeypatch.setattr(build, "_load_interim",
                        lambda name: {"decrees": [decree]} if "jort" in name else None)

    appointments = pd.DataFrame([
        {"appointment_id": "A1", "person_id": "P-mzali",
         "person_name": "Mohamed Mzali", "portfolio": "head_of_government",
         "start_date": "1980-04-24"},
        {"appointment_id": "A2", "person_id": "P-salah-mzali",
         "person_name": "Mohamed Salah Mzali", "portfolio": "education",
         "start_date": "1980-04-24"},
    ])
    out = build.attach_jort_citations(appointments.copy()).set_index("appointment_id")
    assert out.loc["A1", "jort_citation"] == "JORT 1980, N°028, p. 2 (fr)"
    assert pd.isna(out.loc["A2", "jort_citation"])
    assert out.loc["A1", "jort_match_basis"] == "office_and_date"


def test_a_year_only_decree_matches_within_its_year_and_not_by_day(monkeypatch):
    """Before about 1980 the gazette's issue pages carry no publication date.

    Those decrees were unusable and never matched - which lost the
    prime-ministerial appointments of Nouira, Mzali, Sfar and Baccouche. Dated
    to the year, they match inside that calendar year only, and never claim a
    day-level gap they cannot support.
    """
    from govtn import build

    decree = {
        "citation": "JORT 1979, N°064, p. 2 (fr)", "year": 1979, "issue": "064",
        "page": 2, "lang": "fr", "kind": "nomination", "portfolio_hint": None,
        "holder": "Hédi NOUIRA", "office": "Premier Ministre",
        "effective": None, "published": None, "snippet": "",
        "query": "", "url": "https://jort.tn/x",
    }
    monkeypatch.setattr(build, "_load_interim",
                        lambda name: {"decrees": [decree]} if "jort" in name else None)

    appointments = pd.DataFrame([
        {"appointment_id": "IN", "person_id": "P1", "person_name": "Hédi Nouira",
         "portfolio": "head_of_government", "start_date": "1979-09-01"},
        {"appointment_id": "OUT", "person_id": "P1", "person_name": "Hédi Nouira",
         "portfolio": "head_of_government", "start_date": "1978-09-01"},
    ])
    out = build.attach_jort_citations(appointments.copy()).set_index("appointment_id")
    assert out.loc["IN", "jort_citation"] == "JORT 1979, N°064, p. 2 (fr)"
    assert out.loc["IN", "jort_date_kind"] == "year_only"
    # No day-level gap is asserted for a decree dated only to its year.
    assert pd.isna(out.loc["IN", "jort_date_delta"])
    # A different year does not match at all.
    assert pd.isna(out.loc["OUT", "jort_citation"])


def test_the_gazette_name_is_published_beside_ours(harvested):
    """A citation matched on a name must be checkable without re-running it.

    Takes `harvested`, not `tables`: a clone with no payloads under
    `data/interim/` falls back to the 23-row curated spine, which carries no
    `jort_*` columns at all, so this raised KeyError on `jort_citation` rather
    than reporting anything about citation quality.
    """
    appointments = harvested["appointments"]
    cited = appointments[appointments["jort_citation"].notna()]
    assert not cited.empty
    assert cited["jort_holder"].notna().all()
    from govtn.normalize import name_similarity
    worst = min(name_similarity(str(a), str(b))
                for a, b in zip(cited["person_name"], cited["jort_holder"]))
    assert worst >= 0.75, f"a citation was accepted at similarity {worst}"
