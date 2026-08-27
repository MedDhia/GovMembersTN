"""Network construction and export.

Four graphs are produced, because "the network of Tunisian ministers" is not
one object and the choice between them is a substantive one:

  1. BIPARTITE person-cabinet affiliation. The primitive; everything else is a
     projection of it. Keep this if you intend to run bipartite-aware methods
     rather than a projection.

  2. CO-MEMBERSHIP (person-person, undirected, weighted). Two ministers are
     tied if they sat in the same cabinet AT THE SAME TIME. The temporal
     qualifier is the point: simply sharing a cabinet label connects people
     whose tenures never overlapped, because cabinets are reshuffled
     constantly and a "cabinet" can span years. Edge weight is days of
     overlap, so a fortnight's coincidence is not scored like a decade
     together.

  3. SUCCESSION (person-person, DIRECTED). An edge runs from a minister to
     whoever next held the same portfolio. This is the portfolio-inheritance
     structure, and it is what you want for questions about the circulation
     of specific posts rather than about co-presence.

  4. HOMOPHILY (person-person, undirected, typed). Ties from shared
     institutional background - same university, same birth region, same
     party. These are POTENTIAL channels, not observed interactions, and
     mixing them into the co-membership graph would conflate co-presence with
     background similarity. They are kept as a separate, separately typed
     layer for exactly that reason.

Exports are written as edge-list CSVs (for igraph/statnet/Gephi import) and as
GEXF and GraphML with node attributes attached (for Gephi/Cytoscape directly).
"""

from __future__ import annotations

import argparse
import itertools
import logging
from datetime import date
from typing import Any, Iterable

import networkx as nx
import pandas as pd

from . import config

log = logging.getLogger(__name__)

# Below this, a co-membership tie is an artefact of a reshuffle rather than a
# working relationship. Exposed as a parameter because the right value is a
# research decision, not a fact.
DEFAULT_MIN_OVERLAP_DAYS = 30

# Explicit column schemas. An edge layer can legitimately come out empty - a
# dataset of heads of government alone has no co-membership ties - and an
# empty CSV with no header row is unreadable by pandas, R and Gephi alike.
# Writing the header regardless keeps every export loadable.
EDGE_SCHEMA = {
    "co_membership": ["source", "target", "weight", "overlap_days", "overlap_years",
                      "n_cabinets", "cabinets", "eras", "tie_type"],
    "succession": ["source", "target", "portfolio", "handover_date",
                   "predecessor_tenure_days", "era", "weight", "tie_type"],
    "homophily": ["source", "target", "tie_type", "weight", "shared_values"],
    "bipartite": ["person_id", "cabinet_id", "n_posts", "portfolios",
                  "tenure_days", "era"],
}


def _with_schema(frame: pd.DataFrame, layer: str) -> pd.DataFrame:
    """Guarantee the declared columns exist, even on an empty result."""
    columns = EDGE_SCHEMA[layer]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[columns]

# Person attributes carried onto graph nodes. Kept small: Gephi and GraphML
# both cope badly with very wide attribute tables.
# `birth_region` here is Wikidata's raw P131 label - a delegation, not a
# governorate. It is exported for provenance, but the harmonised coding is what
# anyone partitioning or colouring a graph by region actually wants, so
# `birth_governorate` and `birth_region_type` travel with it.
NODE_ATTRIBUTES = [
    "name", "gender", "birth_year", "birth_place", "birth_region",
    "birth_governorate", "birth_region_type", "birth_coastal", "birth_sahel",
    "birth_country", "birth_abroad",
    "education", "parties", "profession_domains", "n_appointments",
    "n_cabinets", "total_tenure_days", "ever_sovereign_portfolio",
    "ever_head_of_government", "eras_served", "wikidata_qid",
]


def _as_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _overlap_days(a: pd.Series, b: pd.Series, censor: date) -> int:
    a_start, b_start = _as_date(a["start_date"]), _as_date(b["start_date"])
    if a_start is None or b_start is None:
        return 0
    a_end = _as_date(a["end_date"]) or censor
    b_end = _as_date(b["end_date"]) or censor
    return max(0, (min(a_end, b_end) - max(a_start, b_start)).days)


# ---------------------------------------------------------------------------
# 1. Bipartite affiliation
# ---------------------------------------------------------------------------

def bipartite_edges(appointments: pd.DataFrame) -> pd.DataFrame:
    """person -> cabinet affiliation edges."""
    frame = appointments.dropna(subset=["person_id", "cabinet_id"])
    edges = (
        frame.groupby(["person_id", "cabinet_id"])
        .agg(
            n_posts=("appointment_id", "count"),
            portfolios=("portfolio", lambda s: "|".join(sorted(set(s)))),
            tenure_days=("tenure_days", "sum"),
            era=("era", "first"),
        )
        .reset_index()
    )
    return _with_schema(edges, "bipartite")


# ---------------------------------------------------------------------------
# 2. Co-membership projection
# ---------------------------------------------------------------------------

def co_membership_edges(
    appointments: pd.DataFrame,
    *,
    min_overlap_days: int = DEFAULT_MIN_OVERLAP_DAYS,
    censor: date | None = None,
) -> pd.DataFrame:
    """Person-person ties weighted by days of overlapping cabinet service."""
    censor = censor or config.snapshot_date()
    frame = appointments.dropna(subset=["person_id", "cabinet_id"])
    accumulator: dict[tuple[str, str], dict[str, Any]] = {}

    for cabinet_id, group in frame.groupby("cabinet_id"):
        # One row per person per cabinet: a minister holding two portfolios in
        # the same cabinet must not be counted as two co-members.
        people = (
            group.sort_values("start_date")
            .groupby("person_id")
            .agg(start_date=("start_date", "min"), end_date=("end_date", "max"),
                 era=("era", "first"))
            .reset_index()
        )
        for (_, left), (_, right) in itertools.combinations(people.iterrows(), 2):
            overlap = _overlap_days(left, right, censor)
            if overlap < min_overlap_days:
                continue
            key = tuple(sorted((left["person_id"], right["person_id"])))
            entry = accumulator.setdefault(key, {
                "overlap_days": 0, "n_cabinets": 0, "cabinets": [], "eras": set(),
            })
            entry["overlap_days"] += overlap
            entry["n_cabinets"] += 1
            entry["cabinets"].append(str(cabinet_id))
            if pd.notna(left["era"]):
                entry["eras"].add(str(left["era"]))

    rows = [
        {
            "source": a, "target": b,
            "weight": data["overlap_days"],
            "overlap_days": data["overlap_days"],
            "overlap_years": round(data["overlap_days"] / 365.25, 2),
            "n_cabinets": data["n_cabinets"],
            "cabinets": "|".join(sorted(set(data["cabinets"]))),
            "eras": "|".join(sorted(data["eras"])),
            "tie_type": "co_membership",
        }
        for (a, b), data in accumulator.items()
    ]
    return _with_schema(pd.DataFrame(rows), "co_membership")


# ---------------------------------------------------------------------------
# 3. Portfolio succession
# ---------------------------------------------------------------------------

def succession_edges(appointments: pd.DataFrame) -> pd.DataFrame:
    """Directed predecessor -> successor edges within each portfolio."""
    frame = appointments.dropna(subset=["person_id", "portfolio", "start_date"])
    frame = frame[frame["portfolio"] != "other"]
    rows = []
    for portfolio, group in frame.groupby("portfolio"):
        ordered = group.sort_values("start_date")
        # Collapse consecutive rows for the same person: a reshuffle that
        # reappoints the same minister is not a succession event.
        sequence = []
        for _, row in ordered.iterrows():
            if sequence and sequence[-1]["person_id"] == row["person_id"]:
                continue
            sequence.append(row)
        for previous, following in zip(sequence, sequence[1:]):
            rows.append({
                "source": previous["person_id"],
                "target": following["person_id"],
                "portfolio": portfolio,
                "handover_date": following["start_date"],
                "predecessor_tenure_days": previous.get("tenure_days"),
                "era": following.get("era"),
                "weight": 1,
                "tie_type": "succession",
            })
    return _with_schema(pd.DataFrame(rows), "succession")


# ---------------------------------------------------------------------------
# 4. Background homophily
# ---------------------------------------------------------------------------

# Values too generic to constitute a meaningful shared background: linking
# every "Indépendant" to every other would produce one enormous fake clique.
_GENERIC_VALUES = {
    "independant", "independent", "sans parti", "none", "nan", "unknown",
    "aucun", "mustaqill",
}


def homophily_edges(
    persons: pd.DataFrame,
    *,
    attributes: Iterable[str] = ("education", "birth_governorate", "parties"),
    max_group_size: int = 60,
) -> pd.DataFrame:
    """Ties from shared multi-valued background attributes.

    Groups larger than `max_group_size` are dropped rather than expanded:
    a shared value held by hundreds of people is a category, not a tie, and
    turning it into a clique would add O(n^2) edges that swamp the graph.
    Birth of Tunis is dropped for exactly this reason, which is the right
    answer: a sixth of all ministers were born in the capital, and that is a
    fact about the capital rather than a connection between any two of them.

    Regional ties use `birth_governorate`, not the raw Wikidata `birth_region`
    label. `birth_region` is a P131 value naming a delegation, so it both
    splits one governorate across many labels and is absent for everyone whose
    settlement was coded from `config/places.yml` instead - it produced
    scattered ties among the well-documented and none at all for the rest.
    Dropped groups are logged so the omission is visible.
    """
    from .normalize import clean_name

    rows = []
    for attribute in attributes:
        if attribute not in persons.columns:
            log.warning("no %s column - skipping that homophily layer", attribute)
            continue
        index: dict[str, list[str]] = {}
        for _, person in persons.iterrows():
            raw = person.get(attribute)
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            for value in str(raw).split("|"):
                key = clean_name(value)
                if not key or key in _GENERIC_VALUES or len(key) < 3:
                    continue
                index.setdefault(key, []).append(person["person_id"])

        for value, members in index.items():
            members = sorted(set(members))
            if len(members) < 2:
                continue
            if len(members) > max_group_size:
                log.info(
                    "homophily: dropping %r on %s (%d members > max_group_size)",
                    value, attribute, len(members),
                )
                continue
            for a, b in itertools.combinations(members, 2):
                rows.append({
                    "source": a, "target": b,
                    "tie_type": f"shared_{attribute}",
                    "shared_value": value,
                    "weight": 1,
                })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return _with_schema(frame, "homophily")
    # Collapse duplicate ties of the same type, keeping a count.
    collapsed = (
        frame.groupby(["source", "target", "tie_type"])
        .agg(weight=("weight", "sum"),
             shared_values=("shared_value", lambda s: "|".join(sorted(set(s)))))
        .reset_index()
    )
    return _with_schema(collapsed, "homophily")


# ---------------------------------------------------------------------------
# Graph assembly and export
# ---------------------------------------------------------------------------

def _node_attributes(persons: pd.DataFrame) -> dict[str, dict[str, Any]]:
    columns = [c for c in NODE_ATTRIBUTES if c in persons.columns]
    attributes: dict[str, dict[str, Any]] = {}
    for _, person in persons[["person_id", *columns]].iterrows():
        # OMIT missing values rather than writing an empty string. GEXF and
        # GraphML infer each attribute's type from the values present, so a
        # numeric column containing "" is declared numeric and then fails to
        # parse on read - `nx.read_gexf` raised
        # "could not convert string to float: ''" and the exported graph could
        # not be loaded at all. Both formats allow an attribute to be absent
        # on a node, which is the correct encoding of "not recorded".
        attributes[person["person_id"]] = {
            column: person[column]
            for column in columns
            if not pd.isna(person[column])
        }
    return attributes


def build_graph(
    edges: pd.DataFrame, persons: pd.DataFrame, *, directed: bool = False
) -> nx.Graph:
    graph = nx.DiGraph() if directed else nx.Graph()
    attributes = _node_attributes(persons)
    for person_id, values in attributes.items():
        graph.add_node(person_id, **values)
    if not edges.empty:
        for _, edge in edges.iterrows():
            payload = {
                key: value
                for key, value in edge.items()
                if key not in {"source", "target"} and not pd.isna(value)
            }
            graph.add_edge(edge["source"], edge["target"], **payload)
    # Isolates are people with no qualifying tie. They are kept deliberately:
    # dropping them would bias any centrality distribution computed from the
    # result by silently removing the zero-degree cases.
    return graph


def add_centrality(graph: nx.Graph) -> nx.Graph:
    """Attach the standard centrality measures as node attributes."""
    if graph.number_of_nodes() == 0:
        return graph
    undirected = graph.to_undirected() if graph.is_directed() else graph
    nx.set_node_attributes(graph, dict(undirected.degree()), "degree")
    nx.set_node_attributes(
        graph, dict(undirected.degree(weight="weight")), "weighted_degree"
    )
    nx.set_node_attributes(graph, nx.betweenness_centrality(undirected), "betweenness")
    nx.set_node_attributes(graph, nx.closeness_centrality(undirected), "closeness")
    try:
        nx.set_node_attributes(
            graph, nx.eigenvector_centrality(undirected, max_iter=1000), "eigenvector"
        )
    except (nx.PowerIterationFailedConvergence, nx.NetworkXException) as exc:
        log.warning("eigenvector centrality not computed: %s", exc)
    return graph


def run(*, min_overlap_days: int = DEFAULT_MIN_OVERLAP_DAYS) -> dict[str, Any]:
    paths = config.paths().ensure()
    appointments = pd.read_csv(paths.processed / "appointments.csv")
    persons = pd.read_csv(paths.processed / "persons.csv")

    layers = {
        "bipartite": bipartite_edges(appointments),
        "co_membership": co_membership_edges(appointments, min_overlap_days=min_overlap_days),
        "succession": succession_edges(appointments),
        "homophily": homophily_edges(persons),
    }
    for name, frame in layers.items():
        path = paths.processed / f"edges_{name}.csv"
        frame.to_csv(path, index=False)
        log.info("wrote %-26s %6d edges", path.name, len(frame))

    graphs = {
        "co_membership": build_graph(layers["co_membership"], persons),
        "succession": build_graph(layers["succession"], persons, directed=True),
    }
    for name, graph in graphs.items():
        add_centrality(graph)
        for extension, writer in (("gexf", nx.write_gexf), ("graphml", nx.write_graphml)):
            path = paths.processed / f"network_{name}.{extension}"
            writer(graph, path)
        log.info(
            "wrote network_%s.{gexf,graphml}  %d nodes, %d edges, density %.4f",
            name, graph.number_of_nodes(), graph.number_of_edges(),
            nx.density(graph),
        )
    return {"edges": layers, "graphs": graphs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-overlap-days", type=int, default=DEFAULT_MIN_OVERLAP_DAYS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(min_overlap_days=args.min_overlap_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
