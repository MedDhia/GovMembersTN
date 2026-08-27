"""03 - Networks: co-membership degree and regional assortativity.

    python analysis/python/03_networks.py

Needs pandas. networkx is optional; if installed the script adds community
detection, and says so when it is not. `analysis/R/03_networks.R` is the same
computation in base R and produces the same coefficients.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from load_govtn import load  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "output" / "tables"
OUT.mkdir(parents=True, exist_ok=True)

persons = load("persons")
edges = load("edges_co_membership")

print(f"Co-membership network: {len(persons)} nodes, {len(edges)} edges")
print("Edge weight is DAYS OF OVERLAPPING SERVICE, not a count of shared cabinets.")

# --- Degree and weighted degree --------------------------------------------
# The edge list is undirected and stored once per pair, so each endpoint has to
# be counted on both sides.
endpoints = pd.concat([edges.source, edges.target], ignore_index=True)
weights = pd.concat([edges.weight, edges.weight], ignore_index=True)

central = (pd.DataFrame({"person_id": endpoints, "weight": weights})
           .groupby("person_id")
           .agg(degree=("weight", "size"), weighted_degree=("weight", "sum"))
           .reset_index()
           .merge(persons[["person_id", "name", "birth_governorate",
                           "n_appointments"]], on="person_id", how="left")
           .sort_values("degree", ascending=False))

print("\nMost connected ministers by co-membership degree")
print(central[["name", "degree", "weighted_degree", "n_appointments"]]
      .head(10).to_string(index=False))
central.to_csv(OUT / "03_centrality.csv", index=False)

# --- Regional assortativity -------------------------------------------------
# Nominal assortativity on region of birth: a direct test of regional closure.
#
# Use birth_governorate, NOT birth_region. The latter is Wikidata's raw P131
# label, which names a delegation - several hundred near-unique categories that
# drive the coefficient towards zero and make closure look absent.
#
# Vertices with no coded governorate are dropped rather than pooled: ministers
# born abroad have no governorate by design, and letting NA become its own
# category would count "born abroad" as a region and inflate the coefficient.
attr_of = dict(zip(persons.person_id, persons.birth_governorate))
a = edges.source.map(attr_of)
b = edges.target.map(attr_of)
keep = a.notna() & b.notna()
print(f"\nEdges with both endpoints coded: {int(keep.sum())} of {len(edges)}")


def assortativity(left: pd.Series, right: pd.Series,
                  weight: pd.Series | None = None) -> float:
    """Newman's nominal assortativity from the edge mixing matrix."""
    w = pd.Series(1.0, index=left.index) if weight is None else weight.astype(float)
    frame = pd.DataFrame({"a": left, "b": right, "w": w})
    # Each undirected edge contributes to both cells, so the matrix is symmetric.
    both = pd.concat([frame, frame.rename(columns={"a": "b", "b": "a"})])
    mixing = both.pivot_table(index="a", columns="b", values="w",
                              aggfunc="sum", fill_value=0.0)
    mixing = mixing.reindex(index=mixing.columns.union(mixing.index),
                            columns=mixing.columns.union(mixing.index),
                            fill_value=0.0)
    e = mixing.to_numpy()
    e = e / e.sum()
    trace = e.trace()
    squared = float((e.sum(axis=1) * e.sum(axis=0)).sum())
    return (trace - squared) / (1 - squared)


r_plain = assortativity(a[keep], b[keep])
r_weighted = assortativity(a[keep], b[keep], edges.weight[keep])
print(f"Assortativity by governorate of birth: {r_plain:.4f} (unweighted), "
      f"{r_weighted:.4f} (by overlap days)")
print("Near zero means ministers from the same governorate are no more likely to")
print("serve together than chance - co-membership is set by cabinet timing, not origin.")

pd.DataFrame({"measure": ["assortativity_unweighted", "assortativity_weighted"],
              "value": [r_plain, r_weighted]}).to_csv(
    OUT / "03_assortativity.csv", index=False)

# --- Optional: communities --------------------------------------------------
try:
    import networkx as nx

    graph = nx.from_pandas_edgelist(edges, "source", "target", ["weight"])
    communities = nx.community.louvain_communities(graph, weight="weight", seed=1)
    modularity = nx.community.modularity(graph, communities, weight="weight")
    print(f"\nLouvain modularity: {modularity:.3f} across {len(communities)} communities")
except ImportError:
    print("\n(networkx not installed - skipping community detection. "
          "pip install networkx to enable it.)")

print(f"\nWrote 2 tables to {OUT}")
