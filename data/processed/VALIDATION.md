# Data validation report

- Generated: `2026-08-26T14:46:16+00:00`
- Snapshot date: `2026-08-26`
- Harvest complete: **False**
- Errors: **0** | Warnings: **2**

> **This dataset was built from a partial harvest.** Missing sources: `wikidata_persons`, `wikidata_officeholders`.
> Counts below describe what was built, not what exists.

## ℹ️ INFO: Portfolio taxonomy coverage

Every ministerial title was classified.

## ⚠️ WARNING: Individual-level attribute coverage

Person-level attribute coverage across 22 people.

| variable           |   present | coverage   |
|:-------------------|----------:|:-----------|
| birth_date         |         0 | 0.0%       |
| birth_place        |         0 | 0.0%       |
| gender             |         0 | 0.0%       |
| education          |         0 | 0.0%       |
| parties            |         0 | 0.0%       |
| occupations        |         0 | 0.0%       |
| profession_domains |         0 | 0.0%       |
| wikidata_qid       |         0 | 0.0%       |

Below 50% coverage: `birth_date`, `birth_place`, `gender`, `education`, `parties`, `occupations`, `profession_domains`, `wikidata_qid`. Analyses using these variables are effectively conditioned on being well documented, which correlates with seniority and with the post-2011 period.

## ⚠️ WARNING: Temporal coverage by decade

| decade   |   appointments |
|:---------|---------------:|
| 1950s    |              3 |
| 1960s    |              1 |
| 1970s    |              1 |
| 1980s    |              5 |
| 1990s    |              1 |
| 2000s    |              0 |
| 2010s    |              6 |
| 2020s    |              6 |

Decades with no appointments at all: 2000s.

## ℹ️ INFO: Seat conflicts

No cabinet-portfolio seat has conflicting holders.

## ℹ️ INFO: Entity resolution decisions

1 merges accepted, 0 vetoed by a disqualifier. 1 rest on name similarity alone (threshold 0.75).
