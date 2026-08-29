# Figures

Forty-two publication figures built from `data/processed/` alone.

```bash
make figures          # or: python figures/make_figures.py
```

Each figure ships three files: a **`.png`** for screen and README embedding, a
**`.pdf`** (vector) for `\includegraphics`, and a **`.csv`** under `tables/`
holding the exact numbers plotted. The CSV is the table view — every value in
every figure is readable without relying on colour.

The `.png` and `.pdf` files are committed, so a clone or a `make bundle`
archive has the figures without running anything. Regenerating them is
deterministic: every stochastic step — the force layouts in figs. 6, 40 and
42, and the Louvain community detection in fig. 29 — is seeded.

| Figure | Form | What it shows |
|---|---|---|
| `fig01_coverage_by_decade` | Heatmap, sequential | Attribute coverage by decade of first appointment. The `VALIDATION.md` caveat as a picture. |
| `fig02_women_share_by_era` | Column, single hue | Women as a share of ministers, 0% under the protectorate to 32.7% after 2021. |
| `fig03_representation_gini` | Multi-line + CI bands | Territorial representation Gini per era, all three partitions. |
| `fig04_lorenz_curves` | Line, emphasis | The Lorenz curves the index is computed from. |
| `fig05_representation_by_governorate` | Diverging bar | Which governorates sit above and below population parity. |
| `fig06_cabinet_continuity` | Node-link | Cabinets linked by the ministers they share, 1943–2026. |
| `fig07_government_size_over_time` | Line | People holding a ministerial post in each year, 1956–2026. |
| `fig08_rank_composition_by_era` | Stacked bar, ordinal | Seniority mix of appointments, era by era. |
| `fig09_survival_in_office` | Kaplan-Meier | How long an appointment lasts, by the regime that made it. |
| `fig10_turnover_and_renewal` | Multi-line | Appointments per year against first-time entrants. |
| `fig11_sovereign_portfolio_tenure` | Timeline | Succession in the six sovereign portfolios. |
| `fig12_regional_composition_by_era` | Stacked bar | Where ministers were born, era by era. |
| `fig13_region_mixing_matrix` | Heatmap, diverging | Co-membership by region pair, against chance. |
| `fig14_age_at_first_appointment` | Interval | Median and interquartile age on entering government. |
| `fig15_cabinets_served` | Bar | How many governments one person serves in. |
| `fig16_top_centrality` | Bar | The twenty most connected ministers. |
| `fig17_survival_in_office_by_region` | Kaplan-Meier | Tenure in a post, by region of birth. |
| `fig18_survival_in_government_by_regime` | Kaplan-Meier | Tenure in government — seat changes included — by regime of entry. |
| `fig19_survival_in_government_by_region` | Kaplan-Meier | The same career clock, by region of birth. |
| `fig20_exit_and_global_shocks` | Line + markers | Ministerial exit against the global shocks. Descriptive; see below. |
| `fig21_homophily_channels` | Bar, two panels | Which shared attribute carries the homophily layer, and how often they coincide. |
| `fig22_elite_persistence_across_eras` | Heatmap, sequential | Ministers two eras have in common — who survives a regime change. |
| `fig23_succession_within_region` | Bar + reference | Same-region handovers against chance, by era. |
| `fig24_governorate_parity_by_era` | Heatmap, diverging | Ministers per capita against parity, governorate × era. |
| `fig25_coast_sahel_interior` | Multi-line | Coast, narrow Sahel and interior shares, era by era. |
| `fig26_seat_switching_and_career` | Interval | Career length by number of portfolios held. |
| `fig27_degree_distribution` | Histogram | How many colleagues a minister has. |
| `fig28_exposure_vs_brokerage` | Scatter, emphasis | Weighted degree against betweenness. |
| `fig29_communities_are_cohorts` | Heatmap, sequential | Louvain communities against era — they are cohorts. |
| `fig30_assortativity_by_attribute` | Diverging bar | Does any attribute sort who serves with whom? |
| `fig31_network_layers_compared` | Bar, two panels | The four layers on comparable counts. |
| `fig32_homophily_and_co_service` | Bar + baseline | Do shared-attribute pairs actually serve together? |
| `fig33_cohesion_by_era` | Line | Mean colleagues per minister, era by era. |
| `fig34_brokers_span_regimes` | Bar + presence grid | Top betweenness, and the regimes each spans. |
| `fig35_tie_weight_distribution` | Histogram | What a co-membership tie is worth. |
| `fig36_succession_inheritance` | Interval | Successor tenure by predecessor tenure. |
| `fig37_cohort_chords` | Circular chords | The whole layer, ministers ordered by arrival. |
| `fig38_succession_arcs` | Arc diagram | Every handover in the six sovereign portfolios. |
| `fig39_carryover_ribbons` | Chord diagram | Ministers two periods have in common. |
| `fig40_co_membership_backbone` | Node-link | The network after the disparity filter. |
| `fig41_broker_ego_network` | Radial ego | One broker's colleagues, grouped by arrival. |
| `fig42_network_by_era` | Small multiples | The same network drawn once per era. |

## Reading them

**Fig. 1 is the one to read first.** Coverage is a fact about Wikidata and
Wikipedia, not about Tunisian ministers, and it moves by a factor of three
across the series. The 1960s column reads as the best-documented decade at
93–100%; that is fifteen people, and the `n=` under each column is there so the
cell colour is never read without it.

**Fig. 3 does not interpolate across withheld eras.** Four of the nine eras are
withheld by the index for insufficient coverage. Their positions stay on the
axis, shaded, and the series is drawn as a thin faded connector across the gap
rather than a solid line — the segment is visibly not a measurement. Read the
trend within a partition, never the level across partitions.

**Figs. 9, 11, 14, 17, 18, 19 and 26 filter, and say what they dropped.** `build` warns that a
roster row with no individual dates inherits its cabinet's span, which is an
upper bound and not a tenure — so every duration figure keeps only
`date_basis` of `statement` or `row`, and drops the end dates the pipeline
already flagged unreliable. That alone takes the 20-year-plus "tenures" from
108 to 22. Fig. 14 additionally excludes ten implausible ages, three of them
negative: `age_at_first_appointment` in the published table contains a handful
of people whose recorded birth date falls after their first appointment.

**`is_incumbent` is not censoring.** It is defined as `end_date.isna()`, so for
anything before 2011 it usually means the sources never recorded an end, not
that someone is still serving. Fig. 7 therefore bounds an open appointment by
its cabinet, and lets it run to the snapshot only where the cabinet itself has
no end date; fig. 9 censors the twelve genuinely open spells and says so.

**Office and government are different clocks, and the gap is the finding.**
Fig. 9 measures how long one appointment lasts; figs. 18 and 19 measure how
long someone stays in government at all, with the clock surviving a move
between portfolios. Under Ben Ali the median post lasts 6.1 years and the
median career 10.1; under Bourguiba, 2.5 against 8.2. A regime that reshuffles
constantly can look unstable in fig. 9 and stable in fig. 18, because the same
people are moving seats rather than leaving. The cliffs in fig. 18 are regime
endings, not attrition — a career begun under Ben Ali could not outlast
January 2011.

**Fig. 20 is descriptive and says so.** There is no event study here and the
data will not support one. Exit is recorded at reshuffle granularity: in the
18 years a cabinet was formed the median exit rate is 0.55, against 0.06 in
the other 43. Four of the five shocks fall in ordinary years — 1973 at 0.16,
1979 at 0.10, 2008 at 0.03, 2022 at 0.00 — and 2020 coincides with a cabinet
formed for domestic reasons. The economic-portfolio share sits at its 0.19
overall mean in every shock window, on samples as small as one appointment.
Five shocks cannot be separated from the reshuffle calendar, so the figure
draws the calendar and marks the shocks for the reader to judge.

**Fig. 19's regional gap is composition, not staying power.** Pooled, ministers
born in the Sahel show a median career of 7.0 years against Greater Tunis's
4.2. That is an era effect: 30% of Sahel entrants begin under Bourguiba
against 11% of Greater Tunis ones, and within an era of entry the medians
converge — under Ben Ali, 11.3, 10.1, 11.3 and 11.3 years across the four
regions. Split by era before reading anything regional into it. The same
caution applies to fig. 17.

**Figs. 13 and 23 both carry a chance baseline, and both come out at chance.**
Regional origin does not structure who serves alongside whom, and a minister
is no likelier than chance to hand over to someone from their own region. The
protectorate's 68% same-region handover rate in fig. 23 looks like strong
homophily until you see the chance line at 65%: recruitment was already that
concentrated. Without the baseline the figure would state a finding that
isn't there.

**The network layer is a union of cliques, and that governs how to read it.**
Everyone in a cabinet is tied to everyone else, so transitivity is 0.82 by
construction and degree measures *exposure*, not popularity. Two consequences
run through figs. 27–35. Louvain finds six communities at modularity 0.465,
but each one is a cohort (fig. 29) — ties cannot cross time, so the community
structure restates the calendar rather than revealing factions. And the same
composite rosters that inflate fig. 7 inflate tie weights: fig. 35's tail past
20 years is not real shared service, and the spike near degree 175 in fig. 27
is one oversized roster whose members all take the same degree. Treat every
weight as an upper bound.

**Betweenness here is a regime-spanning statistic, not an influence one.**
Because ties cannot cross time, sitting between two cohorts requires having
been in both. All twenty highest-betweenness ministers served under two or
more regimes; among the 707 who served under one, 0.1% clear a betweenness of
0.01, against 17.7% of the 175 who served under two or more (fig. 28).
Exposure does not buy it — the thirteen ministers past 3,000 colleague-years
top out at 0.0095, while the top broker ranks only 30th on exposure. Fig. 34
puts the fifteen highest beside the regimes each of them spans; two span four.

**Figs. 30 and 32 look like they disagree, and do not.** Fig. 30 finds no
attribute sorts co-membership: everything lands inside ±0.05, gender largest
at +0.046 and even that more plausibly cohort than affinity. Fig. 32 finds
that pairs sharing a party co-serve at 4.7× the base rate. The difference is
conditioning. Fig. 32 is unconditional and cohort-confounded — people who
share a small governorate tend to share a generation — while figs. 13 and 30
ask whether origin sorts co-membership *given who was in office*. Both are
true; they answer different questions.

## The drawn networks

Figs. 37–42 are the layer drawn rather than summarised, and each solves the
hairball a different way. **Fig. 37** puts all 862 ministers on a circle
ordered by arrival and draws every one of the 38,287 ties, with the bow of
each chord scaled to its angular span so neighbours stay near the rim and only
distant pairs cross the middle; the cohort blocks emerge without any filtering
or selection. **Fig. 40** filters instead, with Serrano's disparity filter —
which keeps ties that are strong *relative to the person they belong to*, so a
short-career minister keeps their defining colleagues where a flat weight
threshold would just keep the largest cabinets. That leaves 403 ministers and
2,733 ties. **Fig. 42** partitions, drawing each era's own subgraph under
identical layout rules so the shapes are comparable. **Fig. 41** abandons
force layout altogether: a star graph has nothing for a force layout to say,
so the alters are placed on arcs by the period they entered, which makes the
brokerage visible rather than merely computed.

Two things not to read into them. A selection by tie strength would have been
prettier and false — weight is inflated by the composite rosters of fig. 35,
which sit almost entirely under Ben Ali, so the strongest *n* ties hand that
period most of the ink. And in fig. 41 the four colleagues from before 1987
are almost certainly roster artefacts of the same kind, not a 55-year career.

**Fig. 6 is drawn at the cabinet level on purpose.** The person-level
co-membership graph has 832 nodes and 35,211 ties even after discarding every
pair who overlapped by less than a year; as a node-link diagram it is a
hairball with no readable claim in it. Aggregating to the cabinet — an edge is
a shared minister — collapses it to 56 nodes and makes the real structure
visible: governments chain to their neighbours in time. For the person-level
graph, open `data/processed/networks/network_co_membership.gexf` in Gephi and
follow the recipe in [`../docs/NETWORK_ANALYSIS.md`](../docs/NETWORK_ANALYSIS.md).

## Two of them are reproduction tests

`fig03` and `fig04` recompute the representation index from `persons.csv`,
`appointments.csv` and `governorates.csv` rather than re-displaying
`indices/representation_gini.csv`, and assert their answer against the
published file to within 5e-4. A figure that silently disagreed with the table
it illustrates would be worse than no figure. This mirrors what
`analysis/*/02_representation_gini` already does for the index itself.

## Design

Colours come from a validated palette and are used unchanged — no eyeballed
hex. The categorical slots were checked under protanopia and deuteranopia
before any chart code was written; the three-slot subset in figs. 3 and 6
clears the all-pairs gate (worst CVD ΔE 9.2, worst normal-vision ΔE 24.0),
which is the harder test that a scatter or a node-link needs. A fourth slot is
used only in figs. 9 and 12, both adjacent-pairlist forms — lines and stacked
bars — where it clears its own gate (worst CVD ΔE 9.1, normal-vision ΔE 22.9).

Ordered scales take a one-hue ordinal ramp rather than categorical hues, since
swapping two of their categories would change the meaning: chronological
periods in fig. 6, seniority in fig. 8. Fig. 13 encodes polarity around a
meaningful midpoint — above or below chance — so it is diverging, not
sequential. Fig. 11's two alternating shades carry no meaning at all; they only
separate neighbouring blocks where a holding is too short for the surface gap
to read.

Three hues in the palette sit below 3:1 against the chart surface. That is
allowed only with a relief channel, which is what `tables/*.csv` and the direct
labels provide.

Light mode only: these are print figures. There is no interactive layer and no
hover — for a static PDF the table twin is the mechanism that keeps values
reachable.

## Dependencies

`matplotlib`, plus the `pandas` and `networkx` the project already uses. The
loaders in `analysis/` still need nothing but pandas; matplotlib is required
only to *regenerate* the figures, never to read the data or use the committed
images.
