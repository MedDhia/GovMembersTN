# Figures

Six publication figures built from `data/processed/` alone.

```bash
make figures          # or: python figures/make_figures.py
```

Each figure ships three files: a **`.png`** for screen and README embedding, a
**`.pdf`** (vector) for `\includegraphics`, and a **`.csv`** under `tables/`
holding the exact numbers plotted. The CSV is the table view — every value in
every figure is readable without relying on colour.

The `.png` and `.pdf` files are committed, so a clone or a `make bundle`
archive has the figures without running anything. Regenerating them is
deterministic: the one stochastic step, the graph layout in fig. 6, is seeded.

| Figure | Form | What it shows |
|---|---|---|
| `fig01_coverage_by_decade` | Heatmap, sequential | Attribute coverage by decade of first appointment. The `VALIDATION.md` caveat as a picture. |
| `fig02_women_share_by_era` | Column, single hue | Women as a share of ministers, 0% under the protectorate to 32.7% after 2021. |
| `fig03_representation_gini` | Multi-line + CI bands | Territorial representation Gini per era, all three partitions. |
| `fig04_lorenz_curves` | Line, emphasis | The Lorenz curves the index is computed from. |
| `fig05_representation_by_governorate` | Diverging bar | Which governorates sit above and below population parity. |
| `fig06_cabinet_continuity` | Node-link | Cabinets linked by the ministers they share, 1943–2026. |

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
which is the harder test that a scatter or a node-link needs. Fig. 6 colours
chronological periods, which are *ordered*, so it takes a one-hue ordinal ramp
rather than categorical hues — swapping two periods would change the meaning,
which is the test for ordinal.

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
