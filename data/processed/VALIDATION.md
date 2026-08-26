# Data validation report

- Generated: `2026-08-26T20:30:01+00:00`
- Snapshot date: `2026-08-26`
- Harvest complete: **True**
- Errors: **0** | Warnings: **5**

## ⚠️ WARNING: Unclassified ministerial titles (222 rows, 7.0%)

Written in full to `data/interim/unmatched_titles.csv`. Each distinct title below is an alias that should be added to `config/portfolios.yml`.

| raw_title                                                                     |   n |
|:------------------------------------------------------------------------------|----:|
| gouverneur de la Banque centrale de Tunisie                                   |  13 |
| porte-parole du gouvernement tunisien                                         |  11 |
| الكاتب العام للحكومة                                                          |   7 |
| وزيرة الشؤون الثقافية                                                         |   6 |
| وزير البريد والبرق والهاتف                                                    |   5 |
| كاتب دولة                                                                     |   4 |
| Gouverneur de la Banque centrale                                              |   4 |
| directeur des PTT                                                             |   4 |
| delegate of the Government of the Generalitat of Catalonia in Northern Africa |   3 |
| prélat territorial de Tunis                                                   |   3 |
| وزير معتمد لدى الوزير الأول                                                   |   3 |
| كاتب دولة للفلاحة                                                             |   3 |
| Secrétaire d'État aux Postes, Télégraphes et Téléphones                       |   3 |
| Président de la                                                               |   3 |
| وزير الاتصال                                                                  |   3 |

_120 further rows omitted._

## ⚠️ WARNING: Individual-level attribute coverage

Person-level attribute coverage across 889 people.

| variable           |   present | coverage   |
|:-------------------|----------:|:-----------|
| birth_date         |       564 | 63.4%      |
| birth_place        |       494 | 55.6%      |
| gender             |       600 | 67.5%      |
| education          |       330 | 37.1%      |
| parties            |       330 | 37.1%      |
| occupations        |       587 | 66.0%      |
| profession_domains |        42 | 4.7%       |
| wikidata_qid       |       603 | 67.8%      |

Below 50% coverage: `education`, `parties`, `profession_domains`. Analyses using these variables are effectively conditioned on being well documented, which correlates with seniority and with the post-2011 period.

## ℹ️ INFO: Temporal coverage by decade

| decade   |   appointments |
|:---------|---------------:|
| 1950s    |            176 |
| 1960s    |            120 |
| 1970s    |            223 |
| 1980s    |            518 |
| 1990s    |            450 |
| 2000s    |            180 |
| 2010s    |            863 |
| 2020s    |            372 |

213 appointments carry no usable start date.

## ⚠️ WARNING: Cabinet seats with more than one recorded holder (487)

Expected where a portfolio changed hands mid-cabinet; a problem where it reflects a source disagreement or a failed merge. Review before treating these as co-holdings.

| cabinet_id                                   | portfolio         |   n_holders |
|:---------------------------------------------|:------------------|------------:|
| Gouvernement Ben Ali                         | economy_planning  |           4 |
| Gouvernement Ben Ali                         | transport         |           2 |
| Gouvernement Ben Ali                         | youth_sports      |           2 |
| Gouvernement Ben Ammar                       | agriculture       |           3 |
| Gouvernement Ben Ammar                       | economy_planning  |           2 |
| Gouvernement Ben Ammar                       | education         |           2 |
| Gouvernement Ben Ammar                       | equipment_housing |           3 |
| Gouvernement Ben Ammar                       | finance           |           2 |
| Gouvernement Ben Ammar                       | health            |           2 |
| Gouvernement Ben Ammar                       | justice           |           2 |
| Gouvernement Ben Ammar                       | without_portfolio |           3 |
| Gouvernement Bouden/Hachani/Madouri/Zaafrani | agriculture       |           3 |
| Gouvernement Bouden/Hachani/Madouri/Zaafrani | culture           |           2 |
| Gouvernement Bouden/Hachani/Madouri/Zaafrani | defence           |           2 |
| Gouvernement Bouden/Hachani/Madouri/Zaafrani | economy_planning  |           3 |

_472 further rows omitted._

## ⚠️ WARNING: Unmapped birthplaces (66 distinct)

402/494 recorded birthplaces resolved to a governorate (81.4%).

Add each settlement below to the `settlements` map in `config/places.yml`. Until then these people are absent from every regional analysis while still counting in the denominator.

| birth_place        |   n |
|:-------------------|----:|
| Tunisie            |   8 |
| M'saken            |   3 |
| Dar Chaâbane       |   3 |
| Métouia            |   3 |
| Bou Salem          |   2 |
| Téboursouk         |   2 |
| El Hamma           |   2 |
| La Manouba         |   2 |
| Tazarka            |   2 |
| El Ksour           |   2 |
| Khniss             |   2 |
| Paris              |   2 |
| Ezzahra            |   2 |
| Ksibet el-Médiouni |   2 |
| Degache            |   2 |

_51 further rows omitted._

## ⚠️ WARNING: Entity resolution decisions

3395 merges accepted, 1559 vetoed by a disqualifier. 474 rest on name similarity alone (threshold 0.75).

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
