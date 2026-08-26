"""Tests for network construction.

The co-membership tests are the important ones. The whole point of that layer
is that a shared cabinet LABEL is not a tie - only shared cabinet TIME is -
and that distinction is invisible unless it is tested directly.
"""
from datetime import date

import pandas as pd
import pytest

from govtn.networks import (
    bipartite_edges,
    build_graph,
    co_membership_edges,
    homophily_edges,
    succession_edges,
)

CENSOR = date(2026, 1, 1)


def appointments(rows):
    frame = pd.DataFrame(rows)
    frame["appointment_id"] = [f"A{i}" for i in range(len(frame))]
    for column, default in (("tenure_days", 100), ("era", "test"),
                            ("portfolio", "interior")):
        if column not in frame:
            frame[column] = default
    return frame


def test_overlapping_tenures_create_a_weighted_tie():
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1",
         "start_date": "2020-01-01", "end_date": "2021-01-01", "portfolio": "interior"},
        {"person_id": "P2", "cabinet_id": "C1",
         "start_date": "2020-07-01", "end_date": "2021-06-01", "portfolio": "finance"},
    ])
    edges = co_membership_edges(frame, min_overlap_days=1, censor=CENSOR)
    assert len(edges) == 1
    # 2020-07-01 to 2021-01-01
    assert edges.iloc[0]["overlap_days"] == 184
    assert edges.iloc[0]["weight"] == 184


def test_same_cabinet_but_no_overlap_creates_no_tie():
    # The core case: both sat in cabinet C1, but never at the same time.
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1",
         "start_date": "2020-01-01", "end_date": "2020-06-01", "portfolio": "interior"},
        {"person_id": "P2", "cabinet_id": "C1",
         "start_date": "2020-09-01", "end_date": "2021-01-01", "portfolio": "interior"},
    ])
    assert co_membership_edges(frame, min_overlap_days=1, censor=CENSOR).empty


def test_brief_overlap_is_filtered_by_the_threshold():
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1",
         "start_date": "2020-01-01", "end_date": "2020-06-10", "portfolio": "interior"},
        {"person_id": "P2", "cabinet_id": "C1",
         "start_date": "2020-06-01", "end_date": "2021-01-01", "portfolio": "finance"},
    ])
    assert len(co_membership_edges(frame, min_overlap_days=1, censor=CENSOR)) == 1
    assert co_membership_edges(frame, min_overlap_days=30, censor=CENSOR).empty


def test_two_portfolios_in_one_cabinet_is_not_self_co_membership():
    # A minister holding two posts must not become his own co-member, nor be
    # double-counted against a colleague.
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1",
         "start_date": "2020-01-01", "end_date": "2021-01-01", "portfolio": "interior"},
        {"person_id": "P1", "cabinet_id": "C1",
         "start_date": "2020-01-01", "end_date": "2021-01-01", "portfolio": "defence"},
        {"person_id": "P2", "cabinet_id": "C1",
         "start_date": "2020-01-01", "end_date": "2021-01-01", "portfolio": "finance"},
    ])
    edges = co_membership_edges(frame, min_overlap_days=1, censor=CENSOR)
    assert len(edges) == 1
    assert {edges.iloc[0]["source"], edges.iloc[0]["target"]} == {"P1", "P2"}


def test_incumbent_is_censored_not_treated_as_infinite():
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1",
         "start_date": "2025-01-01", "end_date": None, "portfolio": "interior"},
        {"person_id": "P2", "cabinet_id": "C1",
         "start_date": "2025-01-01", "end_date": None, "portfolio": "finance"},
    ])
    edges = co_membership_edges(frame, min_overlap_days=1, censor=CENSOR)
    assert edges.iloc[0]["overlap_days"] == 365


def test_succession_is_directed_and_ordered():
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1", "portfolio": "interior",
         "start_date": "2010-01-01", "end_date": "2012-01-01"},
        {"person_id": "P2", "cabinet_id": "C2", "portfolio": "interior",
         "start_date": "2012-01-01", "end_date": "2014-01-01"},
        {"person_id": "P3", "cabinet_id": "C3", "portfolio": "finance",
         "start_date": "2012-01-01", "end_date": "2014-01-01"},
    ])
    edges = succession_edges(frame)
    assert len(edges) == 1, "successions must not cross portfolios"
    assert edges.iloc[0]["source"] == "P1" and edges.iloc[0]["target"] == "P2"


def test_reappointment_is_not_a_succession_event():
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1", "portfolio": "interior",
         "start_date": "2010-01-01", "end_date": "2012-01-01"},
        {"person_id": "P1", "cabinet_id": "C2", "portfolio": "interior",
         "start_date": "2012-01-01", "end_date": "2014-01-01"},
    ])
    assert succession_edges(frame).empty


def test_unclassified_portfolios_are_excluded_from_succession():
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1", "portfolio": "other",
         "start_date": "2010-01-01", "end_date": "2012-01-01"},
        {"person_id": "P2", "cabinet_id": "C2", "portfolio": "other",
         "start_date": "2012-01-01", "end_date": "2014-01-01"},
    ])
    assert succession_edges(frame).empty, "'other' pools unrelated posts"


def test_homophily_ignores_generic_party_labels():
    persons = pd.DataFrame([
        {"person_id": "P1", "education": "ENA", "parties": "Indépendant"},
        {"person_id": "P2", "education": "ENA", "parties": "Indépendant"},
        {"person_id": "P3", "education": "Sorbonne", "parties": "Indépendant"},
    ])
    edges = homophily_edges(persons, attributes=("education", "parties"))
    assert len(edges) == 1
    assert edges.iloc[0]["tie_type"] == "shared_education"


def test_homophily_drops_oversized_groups():
    persons = pd.DataFrame([
        {"person_id": f"P{i}", "education": "Mass University"} for i in range(30)
    ])
    assert homophily_edges(persons, attributes=("education",), max_group_size=10).empty
    assert not homophily_edges(persons, attributes=("education",), max_group_size=50).empty


def test_isolates_are_retained_in_the_graph():
    # Dropping zero-degree nodes would bias any centrality distribution.
    persons = pd.DataFrame([
        {"person_id": "P1", "name": "A"},
        {"person_id": "P2", "name": "B"},
        {"person_id": "P3", "name": "C"},
    ])
    edges = pd.DataFrame([{"source": "P1", "target": "P2", "weight": 5}])
    graph = build_graph(edges, persons)
    assert graph.number_of_nodes() == 3
    assert graph.degree("P3") == 0


def test_bipartite_collapses_multiple_posts_per_cabinet():
    frame = appointments([
        {"person_id": "P1", "cabinet_id": "C1", "portfolio": "interior",
         "start_date": "2020-01-01", "end_date": "2021-01-01"},
        {"person_id": "P1", "cabinet_id": "C1", "portfolio": "defence",
         "start_date": "2020-01-01", "end_date": "2021-01-01"},
    ])
    edges = bipartite_edges(frame)
    assert len(edges) == 1
    assert edges.iloc[0]["n_posts"] == 2
    assert edges.iloc[0]["portfolios"] == "defence|interior"
