# Analysis recipes

Worked examples for both intended uses. Every snippet runs against
`data/processed/` as produced by `make all`.

---

## Choosing a network layer

| Question | Layer |
|---|---|
| Who worked alongside whom? Cohesion, factions, brokerage. | `edges_co_membership` |
| How does a specific portfolio circulate? Who inherits from whom? | `edges_succession` |
| Is recruitment socially closed? Do the same schools keep supplying ministers? | `edges_homophily` |
| Two-mode methods; cabinets as objects in their own right. | `edges_bipartite` |

The critical distinction is between **co-membership** (observed co-presence in
office) and **homophily** (shared background). They answer different questions
and are deliberately kept in separate files. Combining them without saying so
turns "these two people worked together" and "these two people went to the
same university" into the same edge.

### The overlap threshold is a research decision

`co_membership_edges` drops pairs overlapping less than
`--min-overlap-days` (default 30). Tunisian reshuffles routinely put two
people in the same cabinet for a fortnight; whether that is a tie is your
call, not the pipeline's.

```bash
python -m govtn.networks --min-overlap-days 0    # every overlap counts
python -m govtn.networks --min-overlap-days 180  # only sustained co-service
```

Report the value you used — results are sensitive to it.

---

## Individual-level analysis

### Who enters government, and at what age

```python
import pandas as pd

persons = pd.read_csv("data/processed/persons.csv")

# age_at_first_appointment is empty where birth date is unknown, and that
# missingness is not random: it correlates with seniority and with the
# post-2011 period. Report the base.
known = persons.dropna(subset=["age_at_first_appointment", "birth_year"])
print(f"age known for {len(known)}/{len(persons)} people")
print(known.groupby(known["first_appointment"].str[:3] + "0s")
           ["age_at_first_appointment"].agg(["mean", "median", "count"]))
```

### Recruitment channels by regime

```python
appts = pd.read_csv("data/processed/appointments.csv")
frame = (appts.merge(persons[["person_id", "profession_domains"]], on="person_id")
              .query("is_first_appointment"))

channels = (frame.assign(domain=frame["profession_domains"].str.split("|"))
                 .explode("domain").dropna(subset=["domain"]))
print(pd.crosstab(channels["era"], channels["domain"], normalize="index").round(3))
```

### Elite survival across regime change

The variable that makes this dataset worth building: who stayed.

```python
survivors = persons[persons["eras_served"].str.contains(r"\|", na=False)]
print(survivors[["name", "eras_served", "n_appointments",
                 "total_tenure_days", "ever_sovereign_portfolio"]]
      .sort_values("total_tenure_days", ascending=False))
```

### Portfolio tenure — with the precision filter

```python
# Padded dates would silently inflate durations; date_precision exists to
# stop that. Filter before computing.
usable = appts.query("date_precision == 'day' and tenure_days.notna()")
print(usable.groupby("portfolio")["tenure_days"]
            .agg(["median", "count"])
            .query("count >= 5").sort_values("median"))
```

### Survival analysis of ministerial tenure

```python
from lifelines import KaplanMeierFitter   # pip install lifelines

frame = appts.query("date_precision == 'day'").copy()
frame["event"] = ~frame["is_incumbent"]     # incumbents are right-censored

kmf = KaplanMeierFitter()
for era, group in frame.groupby("era"):
    if len(group) < 10:
        continue
    kmf.fit(group["tenure_days"], group["event"], label=era)
    print(f"{era:18s} median tenure {kmf.median_survival_time_:.0f} days")
```

`is_incumbent` is exactly the censoring indicator such a model needs, which is
why open tenures are censored at a frozen snapshot rather than left empty.

---

## Network analysis

### Load and describe

```python
import networkx as nx

G = nx.read_gexf("data/processed/networks/network_co_membership.gexf")
print(f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
      f"density {nx.density(G):.4f}")

# Isolates are retained on purpose: dropping zero-degree nodes would bias
# any centrality distribution computed from this file.
print(f"{len(list(nx.isolates(G)))} isolates")
```

### Brokerage across regimes

```python
import pandas as pd

between = nx.betweenness_centrality(G, weight=None)
frame = pd.DataFrame({
    "person_id": list(between),
    "betweenness": list(between.values()),
    "name": [G.nodes[n].get("name") for n in between],
    "eras": [G.nodes[n].get("eras_served") for n in between],
})
print(frame.nlargest(15, "betweenness"))
```

Ministers who bridge otherwise disconnected cabinet cohorts score highest;
those spanning a regime boundary are the substantively interesting cases.

### Cabinet cohorts as communities

```python
communities = nx.community.louvain_communities(G, weight="weight", seed=42)
print(f"{len(communities)} communities, "
      f"modularity {nx.community.modularity(G, communities, weight='weight'):.3f}")

for i, community in enumerate(sorted(communities, key=len, reverse=True)[:5]):
    eras = {G.nodes[n].get("eras_served") for n in community}
    print(f"  community {i}: {len(community)} members, eras {sorted(filter(None, eras))}")
```

If communities track cabinet cohorts rather than cutting across them, that is
itself the finding: ministerial cohorts do not mix.

### Period-specific slices

Comparing a 1960s network to a 2010s one directly is confounded by coverage —
build slices explicitly rather than trusting the whole graph.

```python
from govtn.networks import co_membership_edges, build_graph

appts = pd.read_csv("data/processed/appointments.csv")
persons = pd.read_csv("data/processed/persons.csv")

for era in ["bourguiba", "ben_ali", "transition", "second_republic", "saied_exception"]:
    slice_ = appts.query("era == @era")
    edges = co_membership_edges(slice_, min_overlap_days=30)
    graph = build_graph(edges, persons[persons["person_id"].isin(slice_["person_id"])])
    if graph.number_of_nodes():
        print(f"{era:18s} n={graph.number_of_nodes():4d} "
              f"density={nx.density(graph):.4f} "
              f"components={nx.number_connected_components(graph)}")
```

### Portfolio circulation

```python
S = nx.read_gexf("data/processed/networks/network_succession.gexf")
interior = nx.DiGraph((u, v, d) for u, v, d in S.edges(data=True)
                      if d.get("portfolio") == "interior")
print(f"interior chain: {interior.number_of_nodes()} holders")
print(f"cycles (returning ministers): {len(list(nx.simple_cycles(interior)))}")
```

### Homophily as a separate layer

```python
homophily = pd.read_csv("data/processed/networks/edges_homophily.csv")
co = pd.read_csv("data/processed/networks/edges_co_membership.csv")

key = lambda f: set(zip(f["source"], f["target"]))
shared_education = key(homophily.query("tie_type == 'shared_education'"))
served_together = key(co)

overlap = shared_education & served_together
print(f"pairs sharing a university: {len(shared_education)}")
print(f"  of which also served together: {len(overlap)} "
      f"({len(overlap)/max(len(shared_education),1):.1%})")
```

For a proper test of whether background predicts co-service, fit an ERGM or a
QAP correlation rather than reading the raw overlap.

---

## R

```r
library(igraph); library(readr); library(dplyr)

edges   <- read_csv("data/processed/networks/edges_co_membership.csv")
persons <- read_csv("data/processed/persons.csv")

g <- graph_from_data_frame(
  d = edges %>% select(source, target, weight, n_cabinets, eras),
  vertices = persons %>% select(person_id, name, gender, birth_year,
                                birth_governorate, birth_region_type,
                                birth_sahel, eras_served, n_appointments),
  directed = FALSE
)

V(g)$betweenness <- betweenness(g, weights = NA)
communities <- cluster_louvain(g, weights = E(g)$weight)
cat("modularity:", modularity(communities), "\n")

# Assortativity on region of birth - a direct test of regional closure.
#
# Use `birth_governorate` (24 categories) or `birth_region_type` (7), NOT
# `birth_region`: that column is Wikidata's raw P131 label, which names a
# delegation. With several hundred near-unique categories it drives nominal
# assortativity towards zero and makes regional closure look absent.
#
# `assortativity_nominal` has no missing-data handling, so drop the
# uncoded vertices explicitly rather than letting NA become its own
# category - ministers born abroad have no governorate by design, and
# silently treating "born abroad" as a region of its own inflates the
# coefficient.
coded <- induced_subgraph(g, which(!is.na(V(g)$birth_governorate)))
region <- as.factor(V(coded)$birth_governorate)
cat("assortativity by governorate of birth:",
    assortativity_nominal(coded, as.integer(region), directed = FALSE), "\n")
```

For ERGMs, `statnet` reads the same edge list:

```r
library(statnet)
net <- network(as.matrix(edges[, c("source", "target")]),
               matrix.type = "edgelist", directed = FALSE)
# then set vertex attributes from persons.csv and fit
```

---

## Gephi / Cytoscape

Open `network_co_membership.gexf` directly. `degree`, `weighted_degree`,
`betweenness`, `closeness` and `eigenvector` are precomputed as node
attributes, along with `name`, `gender`, `birth_governorate`,
`birth_region_type`, `birth_sahel`, `eras_served` and
`ever_sovereign_portfolio` for sizing and colouring. Partition on
`birth_governorate` or `birth_region_type` rather than `birth_region`, which
is the raw Wikidata delegation label and has far too many categories to
colour usefully. Edge weight is days of
overlapping service — set edge thickness to `weight` and the reshuffle noise
recedes on its own.

---

## Before you report anything

1. Read `data/processed/VALIDATION.md`. It reports coverage by decade and by
   attribute. A seventy-year trend computed over uneven coverage is a trend in
   the sources, not in Tunisian politics.
2. Check `MANIFEST.json` for `"complete": true`. If false, some sources never
   ran.
3. State your `min_overlap_days` and your `date_precision` filter.
4. For claims carrying argumentative weight, verify the underlying
   appointments against the *Journal Officiel* — see
   [SOURCES.md](SOURCES.md).
