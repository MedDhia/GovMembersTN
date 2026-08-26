# GovMembersTN

A reproducible, source-linked dataset of the members of Tunisia's governments
from the first post-independence cabinet (15 April 1956) to the present,
built for both **individual-level analysis** (who gets into government, from
where, with what background, for how long) and **network analysis**
(who served alongside whom, who succeeded whom, who shares a background).

Built from Wikidata, the French and Arabic Wikipedias, and Leaders.com.tn,
with every extracted value traceable to a source URL and a retrieval
timestamp.

---

## What's in it

Harvested from Wikidata, the French and Arabic Wikipedias, minister biography
articles, Leaders.com.tn, and the official government portal tunisie.gov.tn:

| | |
|---|---|
| **902** people who held a post in a Tunisian government | |
| **2,979** appointments | one row per person × cabinet × portfolio |
| **53** cabinets | 1943–2026, spanning 23 government spells |
| **40,892** co-membership ties | weighted by days of overlapping service |
| **1,880** succession ties | directed, within portfolio |
| **7,799** homophily ties | shared university, party or birth region |

Person-level attribute coverage: Wikidata QID 68%, gender 67%, Arabic name
65%, birth date 63%, birthplace 56%, education 37%, party 37%, career flags
38%.
54% of appointments carry a date describing the person rather than the cabinet
(see `date_basis`), and 65% of people have a strictly-dated tenure.
`VALIDATION.md` breaks this down by decade and variable — **read it before
computing any long-run trend**; coverage is markedly better after 1987 than
before.

To rebuild from scratch:

```bash
make install
make preflight    # confirms every source host is reachable
make all          # harvest -> build -> networks -> validate
```

Re-running after a parser change costs zero requests: every payload is cached
under `data/raw/`, and `make offline` rebuilds from that cache alone.

## What you get

| File | Grain | Purpose |
|---|---|---|
| `persons.csv` | one person | Individual-level frame: demographics, education, profession, party, plus derived career variables. |
| `appointments.csv` | one person × cabinet × portfolio | The long-format core. Every office held, with dates, rank, harmonised portfolio and regime context. |
| `cabinets.csv` | one cabinet | Size, composition, share of women, sovereign posts. |
| `spells.csv` | one government spell | The curated spine: 23 governments with heads, dates, eras. |
| `portfolios.csv` | one portfolio | The harmonised portfolio taxonomy. |
| `edges_*.csv` | one tie | Four network layers (see below). |
| `network_*.{gexf,graphml}` | graph | Ready for Gephi / Cytoscape, with centralities precomputed. |
| `MANIFEST.json`, `VALIDATION.md` | — | Provenance and data quality. **Read `VALIDATION.md` first.** |

Full column-by-column documentation: **[docs/CODEBOOK.md](docs/CODEBOOK.md)**.

## The four network layers

"The network of Tunisian ministers" is not one object, and the choice between
these is substantive:

1. **`edges_bipartite`** — person → cabinet affiliation. The primitive.
2. **`edges_co_membership`** — two ministers who sat in a cabinet *at the same
   time*, weighted by days of overlap. The temporal qualifier is the point:
   Tunisian cabinets are reshuffled constantly, so people who share a cabinet
   *label* frequently never overlapped in office.
3. **`edges_succession`** — directed, minister → whoever next held the same
   portfolio. Portfolio inheritance rather than co-presence.
4. **`edges_homophily`** — shared university, birth region or party. These are
   *potential* channels, not observed interaction, and are kept as a separate
   typed layer so they are never silently mixed into co-membership.

Recipes: **[docs/NETWORK_ANALYSIS.md](docs/NETWORK_ANALYSIS.md)**.

## Design decisions that affect your results

- **Portfolios are harmonised.** Tunisian ministries are renamed, merged and
  split constantly. `config/portfolios.yml` maps 35 canonical portfolios to
  their French, Arabic and English variants, so "Secrétaire d'État à
  l'Intérieur" (1958) and "وزير الداخلية" (2021) land in the same category.
  Raw titles are preserved in `appointments.raw_title`.
- **Rank is parsed separately from portfolio.** A secretary of state for
  finance is not the finance minister.
- **Regime eras are half-open intervals.** A government formed on a transition
  date belongs to the incoming regime — Hédi Baccouche, appointed 7 November
  1987, is coded under Ben Ali, not Bourguiba.
- **Birthplaces are coded to governorate and region**, with `birth_sahel`
  reserved for the narrow historical Sahel (Sousse, Monastir, Mahdia) and kept
  distinct from `birth_coastal`, which also covers Greater Tunis, the northeast
  and Sfax. Conflating the two is the usual way this variable goes wrong.
- **Date precision is recorded, never invented.** A source that says "1970"
  yields `1970-01-01` with `date_precision = year`. Filter on it before
  computing durations.
- **Open tenures are censored at a frozen snapshot date**, so re-running the
  pipeline next year does not silently lengthen every incumbent's tenure in an
  already-published table.
- **Entity resolution is transliteration-aware and audited.** "Béji Caïd
  Essebsi", "Beji Caid Essebsi" and "El Béji Caïd Es-Sebsi" are one person;
  "Mohamed Ghannouchi" and "Rached Ghannouchi" are not. Merges resting on name
  evidence alone are logged with their scores in
  `data/interim/reconciliation_audit.json` and summarised in `VALIDATION.md`.

## Repository layout

```
config/
  cabinets.yml            curated spine: 23 government spells, eras, heads of state
  heads_biographical.yml  verified biographical seed for the heads of government
  portfolios.yml          35 harmonised portfolios, 7 cabinet ranks, FR/AR/EN aliases
  places.yml              governorates, regions, settlement -> governorate map
  sources.yml             endpoints, rate limits, crawl policy
src/govtn/
  config.py      paths, config loading, snapshot date
  http.py        cached, rate-limited client with provenance manifests
  normalize.py   transliteration-invariant names, title parsing, multi-script dates
  sources/       wikidata.py, wikipedia.py, leaders.py
  reconcile.py   cross-source entity resolution
  build.py       analysis table assembly
  networks.py    edge lists and graph exports
  validate.py    data quality report
  preflight.py   source reachability check
  pipeline.py    end-to-end runner
data/raw/        cached source payloads + MANIFEST.json per source
data/interim/    harvested JSON, reconciliation audit, unmatched titles
data/processed/  the dataset
docs/            CODEBOOK.md, SOURCES.md, NETWORK_ANALYSIS.md
tests/           111 tests, incl. fixtures reproducing real source markup
```

## Usage

```bash
make install     # dependencies
make preflight   # check every source host is reachable
make all         # full pipeline (needs network access)
make offline     # rebuild from the cached payloads, no network
make build       # re-assemble tables from what has been harvested
make networks    # rebuild edge lists and graph files
make validate    # regenerate VALIDATION.md
make test        # run the test suite
make queries     # print the SPARQL for manual execution
```

Re-running after a parser change costs zero requests: every payload is cached
under `data/raw/` and the caching is also the politeness mechanism.

To freeze the censoring date for a published version:

```bash
python -m govtn.pipeline --snapshot 2026-08-26
```

## Extending it

- **A portfolio landed in `other`.** Its raw title is in
  `data/interim/unmatched_titles.csv`; add an alias to
  `config/portfolios.yml`. Aliases are ordered — declare specific portfolios
  before general ones.
- **A merge is wrong.** Check `data/interim/reconciliation_audit.json`, then
  either add a disqualifier in `govtn.reconcile` or raise
  `NAME_MERGE_THRESHOLD`.
- **A birthplace was not coded.** Add the settlement to `config/places.yml`;
  unmapped birthplaces are left empty, never guessed.
- **A new source.** Add a module under `src/govtn/sources/` that emits
  `SourceRecord`s and appointment dicts, then register it in
  `govtn.build.collect_records` and `govtn.pipeline.STAGES`.

## Caveats

- **Coverage is uneven by design of the sources, not of the pipeline.**
  Wikidata and Wikipedia document the post-2011 period far better than the
  1960s, and senior ministers far better than secretaries of state. Any
  seventy-year trend must be read against the decade coverage table in
  `VALIDATION.md`.
- **Party affiliation is not time-varying.** Wikidata records that someone
  belonged to a party, not when.
- **Education strings are not reconciled to identifiers.** Normalise before
  using as a homophily key.
- **Wikipedia and Leaders are tertiary sources.** Where an appointment carries
  a `jort_citation` it is corroborated by the official gazette; where it does
  not, it rests on encyclopaedic sources alone. See
  [docs/SOURCES.md](docs/SOURCES.md).

## Licence

Code: see [LICENSE](LICENSE). Data derived from Wikidata (CC0) and Wikipedia
(CC BY-SA 4.0); redistribution of the derived tables should preserve CC BY-SA
attribution. Leaders.com.tn content is © Leaders — this repository stores only
extracted structured fields and short verification excerpts, never article
bodies.
