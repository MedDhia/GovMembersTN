# Data validation report

- Generated: `2026-08-27T02:27:07+00:00`
- Snapshot date: `2026-08-26`
- Harvest complete: **True**
- Errors: **0** | Warnings: **3**

## ℹ️ INFO: Unclassified ministerial titles (81 rows, 2.6%)

Written in full to `data/interim/unmatched_titles.csv`. Each distinct title below is an alias that should be added to `config/portfolios.yml`.

| raw_title                                                                                               |   n |
|:--------------------------------------------------------------------------------------------------------|----:|
| Président de la                                                                                         |   3 |
| Secrétaire général de la présidence                                                                     |   2 |
| ministre du Travail                                                                                     |   2 |
| مفوض لإعادة التسكين والإعمار                                                                            |   2 |
| Ministrechargé des Réformes économiques et sociales et de la Coordination avec les ministères concernés |   1 |
| كاتب دولة مكلف بالصندوق الوطني للتضامن 26-26                                                            |   1 |
| كاتب دولة للإعلام                                                                                       |   1 |
| président du Conseil national des régions et des districts                                              |   1 |
| Secrétaire d'État chargé des Affaires arabes et africaines                                              |   1 |
| كاتب دولة مكلف بالشؤون الأفريقية والعربية                                                               |   1 |
| كاتب دولة للمالية والتنمية                                                                              |   1 |
| كاتب الدولة للتعاون الدولي                                                                              |   1 |
| وزير الأشغال العمومية                                                                                   |   1 |
| وزير المال                                                                                              |   1 |
| Secrétaire général de la présidence avec rang de ministre                                               |   1 |

_61 further rows omitted._

## ⚠️ WARNING: Individual-level attribute coverage

Person-level attribute coverage across 884 people.

| variable           |   present | coverage   |
|:-------------------|----------:|:-----------|
| birth_date         |       559 | 63.2%      |
| birth_place        |       489 | 55.3%      |
| gender             |       595 | 67.3%      |
| education          |       327 | 37.0%      |
| parties            |       330 | 37.3%      |
| occupations        |       582 | 65.8%      |
| profession_domains |        42 | 4.8%       |
| wikidata_qid       |       598 | 67.6%      |

Below 50% coverage: `education`, `parties`, `profession_domains`. Analyses using these variables are effectively conditioned on being well documented, which correlates with seniority and with the post-2011 period.

## ℹ️ INFO: Temporal coverage by decade

| decade   |   appointments |
|:---------|---------------:|
| 1950s    |            176 |
| 1960s    |            118 |
| 1970s    |            223 |
| 1980s    |            528 |
| 1990s    |            449 |
| 2000s    |            180 |
| 2010s    |            862 |
| 2020s    |            488 |

85 appointments carry no usable start date.

## ⚠️ WARNING: Cabinet seats with more than one recorded holder (509)

Expected where a portfolio changed hands mid-cabinet; a problem where it reflects a source disagreement or a failed merge. Review before treating these as co-holdings.

| cabinet_id                                   | portfolio          |   n_holders |
|:---------------------------------------------|:-------------------|------------:|
| Gouvernement Ben Ali                         | economy_planning   |           4 |
| Gouvernement Ben Ali                         | presidency_affairs |           2 |
| Gouvernement Ben Ali                         | transport          |           2 |
| Gouvernement Ben Ali                         | youth_sports       |           2 |
| Gouvernement Ben Ammar                       | agriculture        |           3 |
| Gouvernement Ben Ammar                       | economy_planning   |           2 |
| Gouvernement Ben Ammar                       | education          |           2 |
| Gouvernement Ben Ammar                       | equipment_housing  |           3 |
| Gouvernement Ben Ammar                       | finance            |           2 |
| Gouvernement Ben Ammar                       | health             |           2 |
| Gouvernement Ben Ammar                       | ict                |           2 |
| Gouvernement Ben Ammar                       | justice            |           2 |
| Gouvernement Ben Ammar                       | without_portfolio  |           3 |
| Gouvernement Bouden/Hachani/Madouri/Zaafrani | agriculture        |           3 |
| Gouvernement Bouden/Hachani/Madouri/Zaafrani | culture            |           2 |

_494 further rows omitted._

## ℹ️ INFO: Birthplace coding

464/489 recorded birthplaces resolved to a governorate (94.9%). A further 17 were born outside Tunisia and 8 name the country only; both are coded in `birth_country` and carry no governorate by design.

## ⚠️ WARNING: Entity resolution decisions

3396 merges accepted, 1561 vetoed by a disqualifier. 477 rest on name similarity alone (threshold 0.75).

Lowest-scoring name-only merges, which are the ones worth eyeballing:

| left   | right   |   score |
|:-------|:--------|--------:|
| w00664 | w00689  |     0.9 |
| l03859 | l03897  |     0.9 |
| w00041 | w00763  |     0.9 |
| w00292 | w01244  |     0.9 |
| w00044 | w01244  |     0.9 |
| w00461 | w00842  |     0.9 |
| w00076 | l03840  |     0.9 |
| l03771 | l03827  |     0.9 |
| w00073 | l03845  |     0.9 |
| w00084 | l03807  |     0.9 |
| w00085 | l03810  |     0.9 |
| w00268 | l03958  |     0.9 |
| w00361 | l03867  |     0.9 |
| w01163 | w01184  |     0.9 |
| w00208 | l03940  |     0.9 |
| w00650 | d03027  |     0.9 |
| w00340 | w00658  |     0.9 |
| w00340 | l03921  |     0.9 |
| w00365 | w01052  |     0.9 |
| w01163 | w01196  |     0.9 |

_10 further rows omitted._
