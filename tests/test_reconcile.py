"""Tests for cross-source entity resolution.

Each case is a merge that must happen, or a false merge that must not. The
false-merge cases are the ones that matter: a single wrong merge fuses two
careers into one and silently corrupts every network measure computed on the
result.
"""
from govtn.reconcile import Reconciler, SourceRecord as R


def resolve(records):
    reconciler = Reconciler()
    reconciler.add_all(records)
    return reconciler, reconciler.resolve()


def groups_of(mapping):
    out = {}
    for record_id, person_id in mapping.items():
        out.setdefault(person_id, set()).add(record_id)
    return out


def test_merges_across_sources_and_spellings():
    _, mapping = resolve([
        R("wd1", "wikidata", "Béji Caïd Essebsi", qid="Q57553", birth_year=1926),
        R("wp1", "wikipedia", "Beji Caid Essebsi", wikilink="Béji Caïd Essebsi"),
        R("ld1", "leaders", "El Béji Caïd Es-Sebsi", birth_year=1926),
    ])
    assert len(set(mapping.values())) == 1
    # The QID is adopted as the cluster identity.
    assert set(mapping.values()) == {"Q57553"}


def test_distinct_qids_never_merge():
    _, mapping = resolve([
        R("a", "wikidata", "Mohamed Ghannouchi", qid="Q57592"),
        R("b", "wikidata", "Rached Ghannouchi", qid="Q313559"),
    ])
    assert len(set(mapping.values())) == 2


def test_shared_wikilink_merges_differing_display_names():
    _, mapping = resolve([
        R("a", "wikipedia", "Bourguiba", wikilink="Habib Bourguiba"),
        R("b", "wikipedia", "Habib Bourguiba", wikilink="Habib Bourguiba"),
    ])
    assert len(set(mapping.values())) == 1


def test_birth_year_conflict_vetoes_a_name_merge():
    reconciler, mapping = resolve([
        R("x1", "wikipedia", "Ahmed Ben Salah", birth_year=1926),
        R("x2", "leaders", "Ahmed Ben Salah", birth_year=1970),
    ])
    assert len(set(mapping.values())) == 2, "identical names, incompatible birth years"
    assert any(d.rule == "birth_year_conflict" for d in reconciler.rejections)


def test_vetoed_clusters_get_distinct_ids():
    # Regression: the name-derived fallback id must be disambiguated, or two
    # vetoed clusters with the same name collapse back into one person.
    _, mapping = resolve([
        R("x1", "wikipedia", "Ahmed Ben Salah", birth_year=1926),
        R("x2", "leaders", "Ahmed Ben Salah", birth_year=1970),
    ])
    assert mapping["x1"] != mapping["x2"]


def test_same_seat_different_names_do_not_merge():
    reconciler, mapping = resolve([
        R("s1", "wikipedia", "Ahmed Mestiri", cabinet="TN-04", portfolio="interior"),
        R("s2", "wikipedia", "Taieb Mehiri", cabinet="TN-04", portfolio="interior"),
    ])
    assert mapping["s1"] != mapping["s2"]


def test_common_given_names_alone_do_not_merge():
    # Blocking on "Mohamed" must not drag unrelated people together.
    _, mapping = resolve([
        R("a", "wikipedia", "Mohamed Mzali"),
        R("b", "wikipedia", "Mohamed Masmoudi"),
        R("c", "wikipedia", "Mohamed Ennaceur"),
    ])
    assert len(set(mapping.values())) == 3


def test_ids_are_stable_under_input_reordering():
    records = [
        R("a", "wikipedia", "Hédi Nouira"),
        R("b", "leaders", "Hédi Amara Nouira"),
        R("c", "wikipedia", "Mohamed Mzali"),
    ]
    _, first = resolve(records)
    _, second = resolve(list(reversed(records)))
    assert first == second


def test_audit_trail_records_scores():
    reconciler, _ = resolve([
        R("a", "wikipedia", "Hédi Nouira"),
        R("b", "leaders", "Hédi Amara Nouira"),
    ])
    merges = [d for d in reconciler.decisions if d.rule == "name_similarity"]
    assert merges and merges[0].score is not None
