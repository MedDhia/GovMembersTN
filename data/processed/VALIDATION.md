# Data validation report

- Generated: `2026-08-27T10:21:12+00:00`
- Snapshot date: `2026-08-26`
- Harvest complete: **True**
- Errors: **0** | Warnings: **3**

## ℹ️ INFO: Unclassified ministerial titles (77 rows, 2.5%)

Written in full to `data/interim/unmatched_titles.csv`. Each distinct title below is an alias that should be added to `config/portfolios.yml`.

| raw_title                                                  |   n |
|:-----------------------------------------------------------|----:|
| Président de la                                            |   3 |
| Secrétaire général de la présidence                        |   2 |
| ministre du Travail                                        |   2 |
| مفوض لإعادة التسكين والإعمار                               |   2 |
| كاتب دولة مكلف بالصندوق الوطني للتضامن 26-26               |   1 |
| كاتب دولة للإعلام                                          |   1 |
| président du Conseil national des régions et des districts |   1 |
| Secrétaire d'État chargé des Affaires arabes et africaines |   1 |
| كاتب الدولة للشؤون العربية والإفريقية                      |   1 |
| كاتب دولة مكلف بالشؤون الأفريقية والعربية                  |   1 |
| كاتب دولة للمالية والتنمية                                 |   1 |
| كاتب الدولة للتعاون الدولي                                 |   1 |
| وزير الأشغال العمومية                                      |   1 |
| وزير المال                                                 |   1 |
| Secrétaire général de la présidence avec rang de ministre  |   1 |

_57 further rows omitted._

## ⚠️ WARNING: Individual-level attribute coverage

Person-level attribute coverage across 882 people.

| variable           |   present | coverage   |
|:-------------------|----------:|:-----------|
| birth_date         |       536 | 60.8%      |
| birth_place        |       479 | 54.3%      |
| gender             |       573 | 65.0%      |
| education          |       308 | 34.9%      |
| parties            |       323 | 36.6%      |
| occupations        |       561 | 63.6%      |
| profession_domains |        41 | 4.6%       |
| wikidata_qid       |       574 | 65.1%      |

Below 50% coverage: `education`, `parties`, `profession_domains`. Analyses using these variables are effectively conditioned on being well documented, which correlates with seniority and with the post-2011 period.

## ℹ️ INFO: Temporal coverage by decade

| decade   |   appointments |
|:---------|---------------:|
| 1950s    |            179 |
| 1960s    |            118 |
| 1970s    |            223 |
| 1980s    |            528 |
| 1990s    |            448 |
| 2000s    |            180 |
| 2010s    |            860 |
| 2020s    |            506 |

52 appointments carry no usable start date.

## ⚠️ WARNING: Cabinet seats with more than one recorded holder (506)

Expected where a portfolio changed hands mid-cabinet; a problem where it reflects a source disagreement or a failed merge. Review before treating these as co-holdings.

| cabinet_id                                   | portfolio          |   n_holders |
|:---------------------------------------------|:-------------------|------------:|
| Gouvernement Ben Ali                         | economy_planning   |           4 |
| Gouvernement Ben Ali                         | foreign_affairs    |           2 |
| Gouvernement Ben Ali                         | presidency_affairs |           2 |
| Gouvernement Ben Ali                         | transport          |           2 |
| Gouvernement Ben Ali                         | youth_sports       |           2 |
| Gouvernement Ben Ammar                       | agriculture        |           3 |
| Gouvernement Ben Ammar                       | economy_planning   |           2 |
| Gouvernement Ben Ammar                       | education          |           3 |
| Gouvernement Ben Ammar                       | equipment_housing  |           4 |
| Gouvernement Ben Ammar                       | finance            |           3 |
| Gouvernement Ben Ammar                       | health             |           2 |
| Gouvernement Ben Ammar                       | ict                |           3 |
| Gouvernement Ben Ammar                       | justice            |           2 |
| Gouvernement Ben Ammar                       | without_portfolio  |           3 |
| Gouvernement Bouden/Hachani/Madouri/Zaafrani | agriculture        |           3 |

_491 further rows omitted._

## ℹ️ INFO: Birthplace coding

456/479 recorded birthplaces resolved to a governorate (95.2%). A further 15 were born outside Tunisia and 8 name the country only; both are coded in `birth_country` and carry no governorate by design.

## ⚠️ WARNING: Entity resolution decisions

3090 merges accepted, 1120 vetoed by a disqualifier. 729 rest on name similarity alone (threshold 0.75).

Lowest-scoring name-only merges, which are the ones worth eyeballing:

| left   | right   |   score |
|:-------|:--------|--------:|
| s00002 | w00143  |     0.9 |
| w00026 | d02839  |     0.9 |
| w00663 | w00688  |     0.9 |
| s00006 | w00287  |     0.9 |
| l03844 | l03882  |     0.9 |
| w00599 | d02697  |     0.9 |
| w00039 | d03091  |     0.9 |
| w00041 | w00762  |     0.9 |
| w00292 | w01231  |     0.9 |
| w00044 | w01231  |     0.9 |
| w00461 | w00841  |     0.9 |
| l03756 | l03812  |     0.9 |
| w00073 | l03830  |     0.9 |
| w00084 | l03792  |     0.9 |
| w00085 | l03795  |     0.9 |
| w00268 | l03943  |     0.9 |
| w00361 | l03852  |     0.9 |
| w00620 | d02722  |     0.9 |
| w00170 | d02407  |     0.9 |
| w00621 | d02721  |     0.9 |

_22 further rows omitted._
