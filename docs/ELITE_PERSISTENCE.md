# The ministers as surnames

`src/govtn/elite_persistence.py` exports every person in this dataset as a
surname, for a comparison assembled in
[EliteNetworksTN](https://github.com/MedDhia/EliteNetworksTN) that asks whether
the families the Tunisian genealogies record hold position out of proportion to
their share of the population. The denominator is the 2024 electoral register,
built in [ElectionsTN](https://github.com/MedDhia/ElectionsTN).

```bash
make elite-persistence      # about a second
```

Writes `data/processed/elite_persistence/layer_ministers.csv`: **1,089
person-era rows over 882 ministers**.

## One row per person per era

The question is about persistence across regimes, so the unit is the minister
*in a regime*. Someone who served Bourguiba and then Ben Ali is evidence about
both, and counting them once would make the earlier regime look emptier than it
was. Eras come from the eras their appointments fall in, not from
`persons.eras_served`, so that the 52 appointments with no usable date show as
a gap rather than being absorbed into a neighbour. Deduplicate on `person_id`
for a headcount.

| era | person-era rows |
|---|---:|
| ben_ali | 351 |
| second_republic | 246 |
| bourguiba | 147 |
| transition | 137 |
| saied_exception | 74 |
| protectorate | 61 |
| monarchy | 24 |
| protectorate_end | 23 |
| (undated) | 20 |
| beylical | 6 |

The era vocabulary is this repository's own (`data/processed/eras.csv`) and is
written out unchanged; EliteNetworksTN maps it onto its five shared periods.
Pushing one repository's periodisation into another's data would be the wrong
way round.

## Which name is read, and the check that comes free

`persons.csv` names all 882 in Latin and 562 in Arabic. The Latin column is the
only one that covers the roster, so it is what the surname is read from — and
`surname_spine.py` reduces it to consonants, which is what makes it comparable
with an Arabic register.

The 562 named in both scripts are not redundancy. They are a **held-out check
on that reduction**, on ministers rather than on the literary notables it was
originally validated against, and the build prints it on every run:

| reading | the French name reduces to the Arabic one for |
|---|---:|
| plain | **92.3%** |
| allowing the licensed variants | **96.6%** |

The 19 that still disagree were read one by one and none is a failure of the
reduction: seven are women whose two sources pick different surnames from a
compound (سهام البوغديري نمصية against *Sihem Boughdiri*), four are sources
disagreeing on a particle (بالطيب against *Bettaieb*), and the rest are
different names for the same person (خير الدين التونسي against *Kheireddine
Pacha*). The figure is quoted in EliteNetworksTN's
`docs/VALIDATION-persistence.md`.

## Schema

Shared with ElectionsTN and ParliamentariansTN. Surnames are written as
**candidates** — the last token, plus it with each binding particle attached,
longest first — rather than resolved, because only the register can say whether
`Ben Ayed` is a family in its own right or a patronymic, and this repository
does not hold the register.

| column | what |
|---|---|
| `layer` | always `ministers` |
| `person_id` | joins `data/processed/persons.csv` |
| `name_raw`, `script` | the name read, and which script it is in |
| `surname_candidates`, `spine_candidates` | pipe-separated, longest first |
| `period` | this repository's era label |
| `subgroup` | birth governorate, where known |
| `name_ar`, `spine_candidates_ar` | the Arabic name, for the check above |
| `first_year`, `max_rank_level`, `ever_head_of_government`, `birth_governorate` | carried through for cutting |

## What the comparison found

The cabinet is the strongest and the longest-running result in the whole
comparison. **196 surnames the genealogies place in Tunisia before
independence** — under the Husaynid beylik to 1881 or under the colonial
administration from 1881 to 1956, merged into one treatment — are **10.2
times** more common among these 882 people than in the 2024 electoral register
(66 holders, 95% CI 8.1–12.8).

### In the contemporary window

Restricted to **2011–2023**, with each person counted once, the cabinet of 396
carries 19 of them. A bearer of such a surname is **6.8 times more likely**
(95% CI 4.3–10.7) to be a minister in that window than someone who is not —
26.6 per 100,000 bearers against 3.9 per 100,000 of everyone else. Converted
into the group's implied mean status that is **+0.48 SD**, against +0.20 SD
for a member of parliament and +0.55 for a co-shareholder of a listed company.

### Over the whole span this dataset covers

Because this dataset reaches back to the 1940s, it is the only one that can
carry the estimator the surname-mobility literature uses over a real number of
generations. The implied status gap falls monotonically across five periods
and three changes of regime:

| | to 1956 | Bourguiba | Ben Ali | transition | Saied |
|---|---:|---:|---:|---:|---:|
| ratio | 20.9× | 15.4× | 9.3× | 6.3× | 5.5× |
| implied status gap | **0.83 SD** | 0.74 SD | 0.59 SD | 0.47 SD | **0.39 SD** |

That is an intergenerational correlation of **b = 0.79 (0.73–0.86)** per
30-year generation — the rate Clark finds in almost every society he measures.
Parliament, over a comparable span, comes out at 0.50: appointed office
transmits, elected office does not.

The two eras are merged, but the split is still estimable at the headline's
rarity cut, and in this roster it is large: the **beylical** surnames run
**17.0×** and the colonial-era ones **5.1×**. The households that staffed the
beylical ministries kept staffing the republic's.

### The caveats that matter most for these rows

**The control is where this result is tested, and it passes.** The comparison
that matters holds rarity and the surname matching fixed and varies only
whether the genealogies know the family: 11,456 surnames under the same
1,000-voter ceiling, read through the same matcher, that Rodovid never
recorded. They hold 5.10% of the register and turn up in **37 of the 882
ministers, a ratio of 0.8× [0.6–1.1]** — at parity, or just under it. Against
that null the cabinet's 10.2× is a factor of twelve, and it is not something
rarity buys.

**The placebo cannot be tested here**, and is a different question anyway.
Surnames the genealogies first record after 1956 are 16 surnames over 0.047%
of the register, so a cabinet of 396 predicts **0.19** of them; observing none
is the expected outcome under every hypothesis. It also would not settle much
if it could be run: those sixteen surnames are themselves in Rodovid, so the
placebo asks whether old documented notability beats *recent* documented
notability, not whether documented notability beats the rest of the country.
That second question is the control's, above. The ministerial result rests on
it and on the monotone eighty-year decline.

**The baseline is a 2024 register**, so the pre-independence ratio is an order
of magnitude rather than a measurement — though the shape of the decline is
corroborated by the gazette's 45,515 appointees, which move 5.2× → 2.5× over
the same span with intervals of ±0.3.

Full results, figures and limitations: `docs/FINDINGS-persistence.md` in
EliteNetworksTN.
