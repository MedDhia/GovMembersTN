# GovMembersTN

A reproducible, source-linked dataset of the members of Tunisia's governments,
built for both **individual-level analysis** (who gets into government, from
where, with what background, for how long) and **network analysis**
(who served alongside whom, who succeeded whom, who shares a background).

The record centres on the independent republic — 2,945 of 3,136 appointments
fall after April 1956 — and extends backwards through the protectorate and,
thinly, into the beylical ministries: 139 appointments before independence, 9
of them before 1900. Treat the pre-1956 rows as a usable but sparse tail, not
as a comparable series.

Every extracted value is traceable to a source URL and a retrieval timestamp,
and 163 appointments carry a citation to the *Journal Officiel*, the gazette
in which a Tunisian ministerial appointment legally takes effect.

---

## Quick start

Everything below works **offline, on a fresh install, with no pipeline run**.
The tables are committed to the repository; you only need the data.

```bash
git clone --depth 1 https://github.com/MedDhia/GovMembersTN.git
cd GovMembersTN
```

Prefer a download? Grab the ZIP from GitHub, or build a 1.8 MB data-only
archive with `make bundle` — the analysis scripts below run from either.

**R** — base R, no packages to install:

```r
source("analysis/R/load_govtn.R")
tn <- govtn_load_all()          # all tables, correctly typed
nrow(tn$persons)                # 882

govtn_describe("persons", "birth_sahel")   # what does this column mean?
panel <- govtn_panel()          # appointments + person + cabinet attributes
```

**Python** — needs pandas and nothing else:

```python
import sys; sys.path.insert(0, "analysis/python")
from load_govtn import load_all, describe, panel

tn = load_all()
tn["persons"].shape             # (882, 56)
describe("persons", "birth_sahel")
```

Both loaders read column types from `data/processed/codebook.csv`, so dates
arrive as dates and flags as booleans, and Arabic and French names arrive as
UTF-8 rather than mojibake. Neither hard-codes the schema, so neither can drift
out of step with the data.

### Worked examples

```bash
make analysis        # all three scripts, in both languages
```

| Script | What it does |
|---|---|
| `01_descriptives` | Coverage by variable, appointments per decade, women per era. |
| `02_representation_gini` | Rebuilds the territorial representation index **from the raw tables** and checks it against the published file. |
| `03_networks` | Co-membership degree and regional assortativity. |

Each exists in both `analysis/R/` and `analysis/python/` and produces the same
numbers, so a result from one can be checked in the other. `02` is a genuine
reproduction test rather than a re-display: it recomputes the index and fails
loudly if its answer disagrees with `data/processed/indices/`.

---

## What's in it

Harvested from Wikidata; the French and Arabic Wikipedias, both cabinet
rosters and minister biographies; Leaders.com.tn; the official government
portal `tunisie.gov.tn`; and the *Journal Officiel* at `jort.tn`:

| Rows | What |
|---:|---|
| **882** | people who held a post in a Tunisian government |
| **3,136** | appointments — one row per person × cabinet × portfolio |
| **57** | cabinets, 1943–2026, across 23 government spells |
| **38,287** | co-membership ties, weighted by days of overlapping service |
| **1,976** | succession ties, directed, within portfolio |
| **12,613** | homophily ties — shared university, party or birth governorate |
| **163** | appointments carrying a *Journal Officiel* citation |

Person-level attribute coverage: Wikidata QID 65%, occupation 64%, gender 65%,
Arabic name 64%, birth date 61%, birthplace 54%, education 35%, party 37%,
career flags 29%.
50% of appointments carry a date describing the person rather than the
cabinet (see `date_basis`); the rest inherit their cabinet's dates, which
makes their tenure a cabinet fact rather than a personal one. 93% of
appointments have a day-precise start date and 7% no usable date at all.
`VALIDATION.md` breaks this down by decade and variable — **read it before
computing any long-run trend**; coverage is markedly better after 1987 than
before.

## What you get

| File | Grain | Purpose |
|---|---|---|
| `persons.csv` | one person | Individual-level frame: demographics, education, profession, party, plus derived career variables. |
| `appointments.csv` | one person × cabinet × portfolio | The long-format core. Every office held, with dates, rank, harmonised portfolio and regime context. |
| `cabinets.csv` | one cabinet | Size, composition, share of women, sovereign posts. |
| `spells.csv` | one government spell | The curated spine: 23 governments with heads, dates, eras. |
| `portfolios.csv` | one portfolio | The harmonised portfolio taxonomy. |
| `governorates.csv` | one governorate | Region, coastal/Sahel coding and 2024 census population. Join on `birth_governorate`. |
| `eras.csv` | one regime period | Era bounds and labels. Intervals are half-open. |
| `codebook.csv` | one variable | Machine-readable dictionary for all 195 variables: type, coverage, levels, description. |
| `networks/edges_*.csv` | one tie | Four network layers (see below). |
| `networks/network_*.{gexf,graphml}` | graph | Ready for Gephi / Cytoscape, with centralities precomputed. |
| `indices/representation_*.csv` | one era × partition | Territorial representation Gini, its changes, and per-governorate ratios. |
| `MANIFEST.json`, `VALIDATION.md` | — | Provenance and data quality. **Read `VALIDATION.md` first.** |

`governorates.csv` and `eras.csv` exist because `config/` holds those coding
decisions in YAML and base R has no YAML parser: publishing them as CSV is what
lets an R user reproduce a regional or era-level result without a rewrite.

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
4. **`edges_homophily`** — shared university, birth governorate or party.
   These are *potential* channels, not observed interaction, and are kept as a
   separate typed layer so they are never silently mixed into co-membership.
   A value held by more than 60 people is a category rather than a tie and is
   dropped instead of expanded into a clique: birth in Tunis, study at the
   Université de Tunis, and PSD and RCD membership all fall out on that rule.

Recipes: **[docs/NETWORK_ANALYSIS.md](docs/NETWORK_ANALYSIS.md)**.

## Design decisions that affect your results

- **Portfolios are harmonised.** Tunisian ministries are renamed, merged and
  split constantly. `config/portfolios.yml` maps 36 canonical portfolios to
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
  Governorates were resolved through the Wikidata QID each birthplace points
  at, not by matching the settlement name: El Guettar, El Ksar, El Mida and
  Ezzahra each name more than one Tunisian place, and label matching puts them
  in the wrong governorate.
- **Foreign birth is coded, not left blank.** `birth_abroad` and
  `birth_country` separate a genuine finding — the Circassian, Georgian and
  Caucasian origins of the beylical-era administrators, and the French and
  Levantine births of the late protectorate elite — from a settlement missing
  from the map. Check `birth_abroad` before reading an empty
  `birth_governorate` as missing data.
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
README.md  LICENSE  CITATION.cff  Makefile  requirements.txt
GovMembersTN.Rproj        opens the repository as an RStudio project
config/
  cabinets.yml            curated spine: 23 government spells, eras, heads of state
  heads_biographical.yml  verified biographical seed for the heads of government
  portfolios.yml          36 harmonised portfolios, 7 cabinet ranks, FR/AR/EN aliases
  places.yml              governorates, regions, settlement -> governorate map,
                          countries of birth for ministers born abroad
  sources.yml             endpoints, rate limits, crawl policy
src/govtn/
  config.py      paths, config loading, snapshot date
  http.py        cached, rate-limited client with provenance manifests
  normalize.py   transliteration-invariant names, title parsing, multi-script dates
  sources/       wikidata.py, wikipedia.py, biographies.py, leaders.py,
                 govtn_portal.py, jort.py
  reconcile.py   cross-source entity resolution
  build.py       analysis table assembly
  networks.py    edge lists and graph exports
  inequality.py  territorial representation index
  codebook.py    generates the machine-readable data dictionary
  validate.py    data quality report
  preflight.py   source reachability check
  pipeline.py    end-to-end runner
analysis/
  R/             load_govtn.R + 01-03 example scripts (base R, no packages)
  python/        load_govtn.py + the same three examples (pandas)
data/raw/        cached source payloads + MANIFEST.json per source (not tracked)
data/interim/    harvested JSON, reconciliation audit, unmatched titles (not tracked)
data/processed/  THE DATASET - tracked, so a clone needs no pipeline run
  networks/      edge lists and graph exports
  indices/       derived measures computed from the tables
output/          where the example scripts write (not tracked)
docs/            CODEBOOK.md, SOURCES.md, NETWORK_ANALYSIS.md
tests/           250 tests, incl. fixtures reproducing real source markup
```

`data/processed/` is the deliverable and is committed. `src/govtn/` is the
pipeline that produced it — provenance, not a prerequisite. You never need to
run it to use the data.

## Rebuilding it

You do not need any of this to use the data. It is here so the tables can be
audited and regenerated.

```bash
make install     # dependencies
make preflight   # check every source host is reachable
make all         # harvest -> build -> networks -> validate (needs network)
```

Working on the data rather than the harvest:

```bash
make offline     # rebuild from the cached payloads, no network
make build       # re-assemble tables from what has been harvested
make networks    # rebuild edge lists and graph files
make validate    # regenerate VALIDATION.md
make inequality  # territorial representation index
make codebook    # regenerate the machine-readable codebook
make analysis    # run the example analyses in Python and R
make bundle      # zip the data + docs + scripts, without the pipeline
make test        # run the test suite
make queries     # print the SPARQL for manual execution
```

Re-running after a parser change costs zero requests: every payload is cached
under `data/raw/`, and the caching is also the politeness mechanism.

**A clone ships `data/processed/` but not `data/raw/` or `data/interim/`** —
the payloads are too large to track. So `make offline` works only after you
have harvested at least once, and `make build` on a fresh clone would rebuild
from the curated spine alone. It refuses to do so rather than replacing the
published dataset with a 23-row one; pass `--force` if that is genuinely what
you want.

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
- **Territorial representation.** `make inequality` writes a population-weighted
  Gini of ministerial recruitment per era, plus significance tests on each
  era-to-era change. Read the trend, not the level: the level depends on which
  territorial partition you pick, and all three are reported for that reason.
  See [docs/CODEBOOK.md](docs/CODEBOOK.md).
- **A birthplace was not coded.** Add the settlement to the `settlements` map
  in `config/places.yml`, or to `foreign_origins` if it lies outside Tunisia.
  Unmapped birthplaces are left empty, never guessed.
- **A new source.** Add a module under `src/govtn/sources/` that emits
  `SourceRecord`s and appointment dicts, then register it in
  `govtn.build.collect_records` and `govtn.pipeline.STAGES`.

## Caveats

- **Coverage is uneven by design of the sources, not of the pipeline.**
  Wikidata and Wikipedia document the post-2011 period far better than the
  1960s, and senior ministers far better than secretaries of state. Any
  seventy-year trend must be read against the decade coverage table in
  `VALIDATION.md`.
- **The post-2021 cabinets have almost no biographical layer.** Of the 30
  people whose first ministerial post came after July 2021, 7% have a coded
  birthplace. This is not a harvesting gap: of the nine who have a Wikidata
  item, none carries a birthplace, and a search of Arabic Wikipedia for the 36
  unlinked roster names matched no article. Their *appointments* are sound —
  those come from rosters and the gazette — but do not compute person-level
  statistics for the period. See "Coverage after July 2021" in
  [docs/CODEBOOK.md](docs/CODEBOOK.md).
- **Party affiliation is not time-varying.** Wikidata records that someone
  belonged to a party, not when.
- **Education strings are not reconciled to identifiers.** Normalise before
  using as a homophily key.
- **Wikipedia and Leaders are tertiary sources.** Where an appointment carries
  a `jort_citation` it is corroborated by the official gazette; where it does
  not, it rests on encyclopaedic sources alone. See
  [docs/SOURCES.md](docs/SOURCES.md).

## Citing this dataset

> Hammami, Mohamed Dhia. *GovMembersTN: Members of Tunisian Governments,
> 1861–2026*. https://github.com/MedDhia/GovMembersTN

`CITATION.cff` carries the same metadata in machine-readable form; GitHub
renders a "Cite this repository" button from it.

Cite the **snapshot date** in `data/processed/MANIFEST.json` alongside it
(currently `2026-08-26`), not the date you downloaded the files. Open tenures
are censored at that date, so it is what makes a tenure length reproducible.

## Licence

Code: see [LICENSE](LICENSE). Data derived from Wikidata (CC0) and Wikipedia
(CC BY-SA 4.0); redistribution of the derived tables should preserve CC BY-SA
attribution. Leaders.com.tn content is © Leaders — this repository stores only
extracted structured fields and short verification excerpts, never article
bodies.
