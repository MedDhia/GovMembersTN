# Codebook

Every column in `data/processed/*.csv` is documented here. `tests/test_docs.py`
fails if a column exists without an entry, so this file cannot drift from the
data.

Conventions used throughout:

- **Dates** are ISO `YYYY-MM-DD`. Where a source gave only a year or a month,
  the date is padded to the first day and `date_precision` records what was
  actually known. **Never compute durations from a padded date without
  checking `date_precision` first.**
- **Multi-valued fields** are pipe-separated (`Sorbonne|ENA`), never
  comma-separated, because commas occur inside institution names.
- **Open tenures** (`end_date` empty) are censored at the snapshot date
  recorded in `MANIFEST.json`, not left infinite.
- **Missing** is an empty cell. It means "not recorded by any harvested
  source", which is not the same as "did not exist".

---

## `persons.csv` — the individual-level analysis frame

One row per person.

### Identity

| Column | Type | Description |
|---|---|---|
| `person_id` | string | **Primary key.** The Wikidata QID where one exists (`Q57553`), otherwise a slug derived from the person's name (`TN-hedi-nouira`). Slugs get a numeric suffix when two distinct people share a name. Stable across runs. |
| `wikidata_qid` | string | The QID, or empty when the person has no Wikidata item. Its absence is itself informative: it tracks how well documented someone is. |
| `name` | string | Preferred display name (the longest variant observed, which is usually the most complete). |
| `name_variants` | string (piped) | Every normalised spelling encountered across sources. Use this, not `name`, when matching against an external list. |
| `name_ar`, `name_en` | string | Arabic and English labels from Wikidata. |

### Demographics

| Column | Type | Description |
|---|---|---|
| `gender` | string | Controlled vocabulary: `male`, `female`, or empty. Wikidata returns this label in the request language (French first), so the raw values are `masculin`/`féminin`; they are mapped here. Sparse for the pre-1987 period. |
| `birth_date`, `birth_year` | date, int | Birth. `birth_year` is provided because year-precision is often all that is available. |
| `death_date`, `death_year` | date, int | Death. Empty for the living **and** for the undocumented — do not read an empty cell as "alive". |
| `birth_date_precision` | string | `day`, `month` or `year` — what the source actually gave. `1972-01-01` with precision `year` means "born in 1972", not "born on 1 January". |
| `birth_place` | string | Settlement of birth, as given by the source. |
| `birth_governorate` | string | Settlement resolved to its **current** governorate via `config/places.yml`. Boundaries changed over the period (Sidi Bouzid 1973, Ben Arous 1983, Manouba 2000); coding to current boundaries is what keeps a seventy-year series comparable. Empty where the settlement is not in the map — `VALIDATION.md` lists those. |
| `birth_region_type` | string | `greater_tunis`, `northeast`, `northwest`, `centre_east`, `centre_west`, `southeast`, `southwest`. |
| `birth_coastal` | bool | The conventional coastal/interior development cleavage. Note Gabès and Médenine are coastal by geography while belonging to the disadvantaged south — use `birth_region_type` when that matters. |
| `birth_sahel` | bool | The **narrow historical Sahel**: Sousse, Monastir, Mahdia only. Deliberately not the same as `birth_coastal`, which also includes Greater Tunis, the northeast and Sfax. Conflating the two attributes Greater Tunis's weight to the Sahel and is the most common way this variable is got wrong. |
| `birth_region` | string | Raw Wikidata `P131` label for the birthplace. Kept verbatim; use `birth_governorate` for the harmonised coding. |
| `birth_place_qid` | string | QID of the birth settlement, for joining to external geodata. |
| `citizenship` | string | Wikidata `P27` label. |

### Background

| Column | Type | Description |
|---|---|---|
| `education` | string (piped) | Institutions attended, merged from Wikidata `P69` and Leaders biographies. Institution names are **not** reconciled to identifiers — `"Sorbonne"` and `"Université de Paris"` may both appear. Normalise before using as a homophily key. |
| `degrees` | string (piped) | Highest-level credential terms (doctorat, maîtrise, diplôme d'ingénieur). |
| `academic_fields` | string (piped) | Wikidata `P101`. |
| `occupations` | string (piped) | Wikidata `P106` labels — an unstructured vocabulary. |
| `profession_domains` | string (piped) | A **controlled** vocabulary derived from Leaders biographies: `law`, `engineering`, `medicine`, `academia`, `economics`, `finance`, `diplomacy`, `security`, `media`, `labour`, `business`, `civil_service`. Prefer this over `occupations` for coding technocrat/party/security backgrounds. |
| `parties`, `party_qids` | string (piped) | Party affiliation from Wikidata `P102`. **Not time-varying**: Wikidata records that someone belonged to a party, not when. Treat as a career-level attribute. |
| `religion`, `awards` | string (piped) | Wikidata `P140`, `P166`. Both very sparse. |

### Source links

| Column | Type | Description |
|---|---|---|
| `wikipedia_fr`, `wikipedia_ar`, `wikipedia_en` | url | Article URLs. |
| `leaders_url` | url | The Leaders biography the person-level fields were extracted from. |
| `sources` | string (piped) | Which harvesters contributed to this row: `spine`, `wikidata`, `wikipedia`, `leaders`. A row seen by only one source is weaker evidence than one seen by three. |

### Derived career variables

All computed from `appointments.csv`; recomputed on every build.

| Column | Type | Description |
|---|---|---|
| `n_appointments` | int | Number of offices held (rows in `appointments.csv`). |
| `n_cabinets` | int | Distinct cabinets served in. |
| `n_portfolios` | int | Distinct harmonised portfolios held. |
| `first_appointment` | date | Entry into government. |
| `last_appointment_end` | date | End of the last recorded office; censored at the snapshot for incumbents. |
| `total_tenure_days` | int | Days in government, computed as the **union** of the person's appointment intervals, so concurrent posts count once. Treat as an **upper bound**: most rows inherit their dates from the cabinet (see `appointments.date_basis`), and a cabinet's span is longer than any individual's tenure in it. Summing per-appointment tenure instead produced careers of 180+ years. |
| `total_appointment_days` | int | The naive **sum** over appointments, retained only for transparency. It double-counts concurrent posts and reshuffle re-listings. Do not use it as a tenure measure. |
| `tenure_days_dated` | int | The same union, restricted to appointments whose dates describe the person rather than the cabinet (`date_basis` in `statement`, `row`, `spine`). Much sparser, and the **only one of the three suitable for duration or survival analysis**. |
| `max_rank_level` | int | Highest rank attained, as the **minimum** level value (0 = head of government, 6 = secretary-general). Lower is higher. |
| `ever_sovereign_portfolio` | bool | Ever held interior, foreign affairs, justice, defence or finance. |
| `ever_head_of_government` | bool | Ever headed a government. |
| `portfolios_held` | string (piped) | The set of portfolios held, sorted. |
| `eras_served` | string (piped) | Regime eras spanned. More than one marks a survivor across a regime change — the key variable for elite-continuity questions. |
| `age_at_first_appointment` | float | Years at entry. Empty when birth date is unknown. |
| `career_span_years` | float | First appointment to last appointment end. |

---

## `appointments.csv` — the long-format core

One row per person × cabinet × portfolio. This is the table to reshape from;
`persons.csv` and the networks are all derived from it.

| Column | Type | Description |
|---|---|---|
| `appointment_id` | string | **Primary key**, `A00001`. Assigned per build — not stable across builds; join on the substantive keys instead. |
| `record_id` | string | Internal id of the source record this row came from; the join key into `data/interim/reconciliation_audit.json`. |
| `person_id` | string | → `persons.person_id`. |
| `cabinet_id` | string | → `cabinets.cabinet_id`. A spell id (`TN-04`) for spine rows, a Wikipedia article title for harvested rows. |
| `spell_id` | string | → `spells.id`. The government spell containing this appointment. |
| `cabinet_article` | string | Source Wikipedia article, where applicable. |
| `raw_title` | string | **The verbatim title as printed by the source.** Always check this before trusting `portfolio` on an unusual case. |
| `person_name` | string | Name as printed by the source, before reconciliation. |
| `person_wikilink` | string | Wikipedia article target for the officeholder. |
| `portfolio` | string | Harmonised portfolio (→ `portfolios.canonical`). `other` means the taxonomy could not classify `raw_title`; those titles are listed in `data/interim/unmatched_titles.csv`. |
| `portfolio_label` | string | English label. |
| `portfolio_power_rank` | string | `sovereign`, `economic`, `social`, `service`. `sovereign` is the classic *ministères de souveraineté*. |
| `rank` | string | Cabinet rank: `head_of_government`, `deputy_head_of_government`, `minister_of_state`, `delegate_minister`, `secretary_of_state`, `minister`, `state_secretary_general`. Parsed separately from the portfolio, because a secretary of state for finance is not the finance minister. |
| `rank_level` | int | Numeric rank, 0 (highest) to 6. |
| `is_interim` | bool | Title marked *par intérim* / بالنيابة. |
| `start_date`, `end_date` | date | Tenure bounds. `end_date` empty = still in office at the snapshot. |
| `date_precision` | string | `day`, `month`, `year`, or `unknown` — the precision of `start_date` as given by the source. **Filter on this before computing durations.** |
| `tenure_days` | int | Days in office; open tenures censored at the snapshot. Read together with `date_basis` — where that is `cabinet`, this is the cabinet's span, not the person's tenure. |
| `date_basis` | string | Where this row's dates came from: `statement` (a Wikidata P580/P582 qualifier — the person's own tenure), `row` (a date cell in the Wikipedia roster table), `spine` (the curated government spine), `cabinet` (**inherited from the cabinet**, because the source gave no individual dates), `unknown`. About three quarters of rows are `cabinet`. **Filter to `statement`/`row`/`spine` before computing any duration.** |
| `is_incumbent` | bool | `end_date` is empty. |
| `era` | string | Regime era at the start of the tenure (→ `spells.era`). Boundaries are half-open, so a government formed on a transition date is coded to the incoming regime. |
| `president` | string | Head of state at the start of the tenure. |
| `head_of_government` | string | Head of the government this appointment sits in. |
| `start_year` | int | Convenience column for grouping. |
| `appointment_seq` | int | 1-based position in this person's career sequence, ordered by start date. |
| `is_first_appointment` | bool | `appointment_seq == 1`. |
| `replaces` | string | Wikidata `P1365`: the person this appointment's holder succeeded in the post. Populated only for Wikidata rows. Independent of `edges_succession.csv`, which is derived from observed date ordering — where both exist they are a useful cross-check on each other. |
| `replaced_by` | string | Wikidata `P1366`: who succeeded this holder. Same caveats as `replaces`. |
| `party_raw` | string | Party as printed in the Wikipedia roster table, verbatim and unharmonised (`RCD`, `Ennahdha`, `Indépendant`). Populated only for Wikipedia rows. Unlike `persons.parties`, which is career-level, this is attached to a specific appointment and so is the better source for **time-varying** party affiliation — at the cost of being an uncontrolled vocabulary. Normalise before use. |
| `source` | string | `spine`, `wikidata`, `wikipedia:fr`, `wikipedia:ar`, `leaders`. |
| `source_ref` | url/string | The specific URL, Wikidata statement or config file the row came from. |
| `confidence` | string | `high` / `medium` / `low`. `low` marks a Wikidata statement with no tenure qualifiers, i.e. an office known to have been held but not when. |

---

## `cabinets.csv` — observed cabinets

| Column | Type | Description |
|---|---|---|
| `cabinet_id` | string | **Primary key.** |
| `spell_id` | string | → `spells.id`. |
| `head_of_government`, `head_role` | string | Who led it, and under what title (`prime_minister`, `head_of_government`, `president_as_head`). |
| `start_date`, `end_date` | date | Observed bounds, from the roster rather than the spine. |
| `n_members` | int | Distinct people. |
| `n_appointments` | int | Rows in `appointments.csv`; exceeds `n_members` when people hold several posts. |
| `n_women`, `share_women` | int, float | Women in the cabinet. Depends on `persons.gender` coverage — **read alongside gender coverage in `VALIDATION.md`**, since an apparent absence of women before 1983 partly reflects missing gender data. |
| `n_sovereign_posts` | int | Appointments to sovereign portfolios. |
| `era`, `president` | string | Context. |
| `confidence` | string | Inherited from the spine record. |

---

## `spells.csv` — the curated government spine

Direct serialisation of `config/cabinets.yml`. One row per government spell.

| Column | Type | Description |
|---|---|---|
| `id` | string | **Primary key**, `TN-00` … `TN-22`. |
| `head`, `head_role` | string | Head of government and the title held. |
| `start`, `end` | date | Spell bounds; `end` empty for the incumbent. |
| `era` | string | Regime era. |
| `confidence` | string | `high` = dates cross-checked; `medium` = spell certain, exact boundary dates need confirmation. |
| `note` | string | Editorial note on coding decisions. |
| `wikipedia_fr`, `wikipedia_en` | string | Seed article titles for the harvester. |
| `pre_independence` | bool | `TN-00` only — excluded from the post-independence frame. |
| `first_post_independence` | bool | `TN-01`, the first government of independent Tunisia. |
| `resolve_subcabinets` | bool | The spell contains several numbered cabinets/reshuffles resolved at harvest time. |
| `spans_regime_change` | bool | The spell crosses a regime boundary (`TN-10`, Ghannouchi, spans 14 January 2011). Appointments inside it are split at the boundary when `era` is assigned. |

---

## `portfolios.csv` — portfolio reference

| Column | Type | Description |
|---|---|---|
| `canonical` | string | **Primary key**; the value used in `appointments.portfolio`. |
| `label_en`, `label_fr` | string | Display labels. |
| `power_rank` | string | `sovereign`, `economic`, `social`, `service`. |
| `created` | string | Approximate first appearance, for portfolios that did not exist in 1956 (environment, ICT, human rights). Right-censor portfolio time series accordingly. |

---

## Edge lists

All four are person-level except `edges_bipartite.csv`. See
[NETWORK_ANALYSIS.md](NETWORK_ANALYSIS.md) for which to use when.

### `edges_bipartite.csv` — person × cabinet affiliation

| Column | Description |
|---|---|
| `person_id`, `cabinet_id` | The affiliation. |
| `n_posts` | Portfolios held by this person in this cabinet. |
| `portfolios` | Which ones (piped). |
| `tenure_days` | Summed tenure in this cabinet. |
| `era` | Regime era. |

### `edges_co_membership.csv` — undirected, weighted

Two ministers sat in the same cabinet **at the same time**.

| Column | Description |
|---|---|
| `source`, `target` | `person_id`s, sorted so each pair appears once. |
| `weight`, `overlap_days` | Days of overlapping service (identical; `weight` is the conventional name). |
| `overlap_years` | Same quantity in years. |
| `n_cabinets` | Cabinets in which the pair overlapped. |
| `cabinets` | Which ones (piped). |
| `eras` | Eras in which the pair overlapped. |
| `tie_type` | Always `co_membership`. |

### `edges_succession.csv` — directed

An edge runs from a minister to whoever next held the same portfolio.

| Column | Description |
|---|---|
| `source`, `target` | Predecessor → successor. |
| `portfolio` | The portfolio being handed over. |
| `handover_date` | Successor's start date. |
| `predecessor_tenure_days` | How long the predecessor lasted. |
| `era` | Era of the handover. |
| `weight` | Always 1. |
| `tie_type` | Always `succession`. |

### `edges_homophily.csv` — undirected, typed

Shared background, **not** observed interaction.

| Column | Description |
|---|---|
| `source`, `target` | `person_id`s. |
| `tie_type` | `shared_education`, `shared_birth_region`, or `shared_parties`. |
| `shared_values` | The values held in common (piped). |
| `weight` | Number of shared values of that type. |

---

## Graph files

`network_co_membership.{gexf,graphml}` and `network_succession.{gexf,graphml}`
carry the node attributes listed in `govtn.networks.NODE_ATTRIBUTES` plus
`degree`, `weighted_degree`, `betweenness`, `closeness` and `eigenvector`.
Isolates are retained deliberately: dropping zero-degree nodes would bias any
centrality distribution computed from the file.

## `MANIFEST.json` and `VALIDATION.md`

`MANIFEST.json` records the snapshot date, which sources contributed, whether
the harvest was complete, and the row/column inventory. `VALIDATION.md` is the
data quality report — **read it before using the tables**; it reports coverage
holes that are invisible in the tables themselves.
