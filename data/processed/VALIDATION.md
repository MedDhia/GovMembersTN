# Data validation report

- Generated: `2026-08-26T18:19:42+00:00`
- Snapshot date: `2026-08-26`
- Harvest complete: **True**
- Errors: **0** | Warnings: **5**

## ⚠️ WARNING: Unclassified ministerial titles (213 rows, 7.2%)

Written in full to `data/interim/unmatched_titles.csv`. Each distinct title below is an alias that should be added to `config/portfolios.yml`.

| raw_title                                                                     |   n |
|:------------------------------------------------------------------------------|----:|
| gouverneur de la Banque centrale de Tunisie                                   |  13 |
| porte-parole du gouvernement tunisien                                         |  11 |
| الكاتب العام للحكومة                                                          |   7 |
| وزير البريد والبرق والهاتف                                                    |   5 |
| كاتب دولة                                                                     |   4 |
| Gouverneur de la Banque centrale                                              |   4 |
| directeur des PTT                                                             |   4 |
| delegate of the Government of the Generalitat of Catalonia in Northern Africa |   3 |
| prélat territorial de Tunis                                                   |   3 |
| وزير معتمد لدى الوزير الأول                                                   |   3 |
| كاتب دولة للفلاحة                                                             |   3 |
| Secrétaire d'État aux Postes, Télégraphes et Téléphones                       |   3 |
| وزير الاتصال                                                                  |   3 |
| Président de la                                                               |   3 |
| secrétaire général                                                            |   3 |

_117 further rows omitted._

## ⚠️ WARNING: Individual-level attribute coverage

Person-level attribute coverage across 909 people.

| variable           |   present | coverage   |
|:-------------------|----------:|:-----------|
| birth_date         |       468 | 51.5%      |
| birth_place        |       417 | 45.9%      |
| gender             |       491 | 54.0%      |
| education          |        13 | 1.4%       |
| parties            |         0 | 0.0%       |
| occupations        |         0 | 0.0%       |
| profession_domains |        43 | 4.7%       |
| wikidata_qid       |       490 | 53.9%      |

Below 50% coverage: `birth_place`, `education`, `parties`, `occupations`, `profession_domains`. Analyses using these variables are effectively conditioned on being well documented, which correlates with seniority and with the post-2011 period.

## ℹ️ INFO: Temporal coverage by decade

| decade   |   appointments |
|:---------|---------------:|
| 1950s    |            217 |
| 1960s    |            110 |
| 1970s    |            195 |
| 1980s    |            640 |
| 1990s    |            492 |
| 2000s    |             57 |
| 2010s    |            809 |
| 2020s    |            342 |

75 appointments carry no usable start date.

## ⚠️ WARNING: Cabinet seats with more than one recorded holder (460)

Expected where a portfolio changed hands mid-cabinet; a problem where it reflects a source disagreement or a failed merge. Review before treating these as co-holdings.

| cabinet_id                                   | portfolio         |   n_holders |
|:---------------------------------------------|:------------------|------------:|
| Gouvernement Ben Ali                         | economy_planning  |           4 |
| Gouvernement Ben Ali                         | foreign_affairs   |           2 |
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

_445 further rows omitted._

## ⚠️ WARNING: Unmapped birthplaces (56 distinct)

341/417 recorded birthplaces resolved to a governorate (81.8%).

Add each settlement below to the `settlements` map in `config/places.yml`. Until then these people are absent from every regional analysis while still counting in the denominator.

| birth_place        |   n |
|:-------------------|----:|
| Tunisie            |   7 |
| M'saken            |   3 |
| Dar Chaâbane       |   3 |
| Téboursouk         |   2 |
| El Hamma           |   2 |
| La Manouba         |   2 |
| El Ksour           |   2 |
| Khniss             |   2 |
| Paris              |   2 |
| Métouia            |   2 |
| Ksibet el-Médiouni |   2 |
| Degache            |   2 |
| Akouda             |   2 |
| Bou Salem          |   1 |
| Bouhjar            |   1 |

_41 further rows omitted._

## ⚠️ WARNING: Entity resolution decisions

2438 merges accepted, 1039 vetoed by a disqualifier. 1041 rest on name similarity alone (threshold 0.75).

Lowest-scoring name-only merges, which are the ones worth eyeballing:

| left   | right   |   score |
|:-------|:--------|--------:|
| s00002 | w00143  |     0.9 |
| w00026 | d02706  |     0.9 |
| w00664 | w00689  |     0.9 |
| s00006 | w00287  |     0.9 |
| l03681 | l03719  |     0.9 |
| w00039 | d02958  |     0.9 |
| w00041 | w00763  |     0.9 |
| w00292 | w01244  |     0.9 |
| w00044 | w01244  |     0.9 |
| w00461 | w00842  |     0.9 |
| w00076 | l03662  |     0.9 |
| l03593 | l03649  |     0.9 |
| w00073 | l03667  |     0.9 |
| w00084 | l03629  |     0.9 |
| w00085 | l03632  |     0.9 |
| w00268 | l03780  |     0.9 |
| w00361 | l03689  |     0.9 |
| w00170 | d02274  |     0.9 |
| w01163 | w01184  |     0.9 |
| w00208 | l03762  |     0.9 |

_26 further rows omitted._
