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


def test_transitive_merge_cannot_fuse_two_qids():
    """Regression: disqualifiers were pairwise, merges are transitive.

    A(Q1)-B and B-C(Q2) each pass a pairwise check because B carries no QID,
    yet the resulting cluster spans two QIDs - two different people fused into
    one row with their careers merged. The check must run against the CLUSTERS.
    """
    reconciler, mapping = resolve([
        R("a", "wikidata", "Mohamed Ali Nafti", qid="Q1"),
        R("b", "wikipedia", "Mohamed Nafti"),
        R("c", "wikidata", "Mohamed Ali Nafti", qid="Q2"),
    ])
    clusters = {frozenset(v) for v in groups_of(mapping).values()}
    for cluster in clusters:
        qids = {reconciler.records[m].qid for m in cluster if reconciler.records[m].qid}
        assert len(qids) <= 1, f"cluster {cluster} spans {qids}"
    assert any(d.rule == "cluster_spans_multiple_qids" for d in reconciler.rejections)


def test_transitive_merge_respects_birth_year_conflicts():
    reconciler, mapping = resolve([
        R("a", "wikipedia", "Ahmed Ben Salah", birth_year=1926),
        R("b", "leaders", "Ahmed Ben Salah"),
        R("c", "wikidata", "Ahmed Ben Salah", birth_year=1980),
    ])
    for cluster in groups_of(mapping).values():
        years = {reconciler.records[m].birth_year for m in cluster
                 if reconciler.records[m].birth_year}
        assert not years or max(years) - min(years) <= 1


def test_arabic_and_latin_names_merge_through_a_wikidata_alias():
    """Arabic and Latin spellings share no tokens and can never match directly.

    Without the alias bridge, every minister appearing in both the French and
    the Arabic Wikipedia is counted as two people, with their appointments
    split across both.
    """
    _, mapping = resolve([
        R("wd", "wikidata", "Habib Essid", aliases=("الحبيب الصيد",), qid="Q3125311"),
        R("fr", "wikipedia", "Habib Essid"),
        R("ar", "wikipedia", "الحبيب الصيد"),
    ])
    assert len(set(mapping.values())) == 1
    assert set(mapping.values()) == {"Q3125311"}


def test_alias_bridge_does_not_merge_unrelated_people():
    _, mapping = resolve([
        R("a", "wikidata", "Habib Essid", aliases=("الحبيب الصيد",), qid="Q1"),
        R("b", "wikidata", "Ali Larayedh", aliases=("علي العريض",), qid="Q2"),
        R("c", "wikipedia", "علي العريض"),
    ])
    groups = groups_of(mapping)
    assert len(groups) == 2
    assert mapping["b"] == mapping["c"], "Arabic row joins the right person"


def test_biography_qid_gives_roster_only_people_an_identity():
    """A minister who appears only in a cabinet table has no QID of their own.

    Resolving the article's Wikidata item through pageprops is what lets that
    person inherit structured attributes and merge with any other source.
    """
    _, mapping = resolve([
        R("wp", "wikipedia", "Taïeb Mehiri", wikilink="Taïeb Mehiri", qid="Q3508964"),
        R("wd", "wikidata", "Taieb Mehiri", qid="Q3508964"),
    ])
    assert len(set(mapping.values())) == 1
    assert set(mapping.values()) == {"Q3508964"}
