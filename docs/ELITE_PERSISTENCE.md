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

Writes two files to `data/processed/elite_persistence/`:

- `layer_ministers.csv`: 1,066 person-era rows over 871 ministers;
- `layer_minister_appointments.csv`: 1,201 rows, one per person and
  government from independence on, over 783 people, with the head of the
  executive who appointed each government and the ruling coalition behind it.

## Three pre-independence cabinets, filed twice

`appointments.csv` files the cabinets of Slaheddine Baccouche (1943 and 1952)
and of Mohamed Salah Mzali (1954) under the government spells of Hédi
Baccouche (1987) and of Mohamed Mzali (1980). The build matches a cabinet
article to a spell by the head's surname, and the Arabic articles, which carry
no date of their own, then take the later spell's start. Every member appears
twice, once at the cabinet's date and once in 1987 or 1980. The later copies,
29 rows over 24 people, counted ministers of the 1940s and 1950s among
Bourguiba's and Ben Ali's: Habib Djellouli and Mohamed Salah Mzali among them.

Both files drop those copies (`MISDATED` in the module). Eleven of the 24 exist
only there, as the Arabic articles' names that reconciliation never joined to
the French ones (محمد حجوج is Mohamed Hadjouj, الطاهر لخضر is Tahar Lakhdar),
so they leave the roster with their copies: it counts 871 people where it
counted 882. The fix belongs in `build.py`'s `spell_for_article`, which should
not match on a surname alone. It is made in the export because the build reads
harvested files this checkout does not hold.

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
| ben_ali | 335 |
| second_republic | 246 |
| transition | 137 |
| bourguiba | 135 |
| saied_exception | 74 |
| protectorate | 61 |
| (undated) | 25 |
| monarchy | 24 |
| protectorate_end | 23 |
| beylical | 6 |

The era vocabulary is this repository's own (`data/processed/eras.csv`) and is
written out unchanged; EliteNetworksTN maps it onto its five shared periods.
Pushing one repository's periodisation into another's data would be the wrong
way round.

## Which name is read, and the check that comes free

`persons.csv` names all 871 in Latin and 561 in Arabic. The Latin column is the
only one that covers the roster, so it is what the surname is read from.
EliteNetworksTN reads it as a registered Arabic surname through its
Arabic-Latin surname crosswalk (`docs/SURNAME-CROSSWALK.md` there), which is
what makes it comparable with an Arabic register.

The 545 named in both scripts are not redundancy. They are among the names the
crosswalk learns Tunisian spelling from, and among the people it is tested on.
Held out of the build five folds at a time, 92.6% of these ministers have their
Latin surname read as the Arabic surname their own Arabic name carries, and
95.9% of those read at a posterior of 0.9 or more. This file used to run a
check of its own on the consonant reduction the analysis used before. The
check now lives with the crosswalk, where it is cross-validated.

## Schema

Shared with ElectionsTN and ParliamentariansTN. Surnames are written as
candidates — the last token, plus it with each binding particle attached,
longest first — rather than resolved, because only the register can say whether
`Ben Ayed` is a family in its own right or a patronymic, and this repository
does not hold the register.

| column | what |
|---|---|
| `layer` | always `ministers` |
| `person_id` | joins `data/processed/persons.csv` |
| `name_raw`, `script` | the name read, and which script it is in |
| `surname_candidates` | pipe-separated, longest first |
| `period` | this repository's era label |
| `subgroup` | birth governorate, where known |
| `name_ar` | the Arabic name, which the crosswalk trains on |
| `first_year`, `max_rank_level`, `ever_head_of_government`, `birth_governorate` | carried through for cutting |
| `years_in_office` | the calendar years the person held an appointment, pipe-separated: every year from an appointment's start to its end, and only the start year where no end is recorded |

## The governments: who appointed, and with which coalition

`layer_minister_appointments.csv` writes each person once per government they
served in, at their first appointment in it, with the highest rank they held
there. Heads of government are left out: they appoint, and the question is who
they, or the president, chose.

A row's government is read from its start date where the date is a day, and
otherwise from the spell the build filed it under. A cabinet-level date of 1
January is how the build writes a year it could not place, so it is not a day.
The four Saïed-era governments the French article lumps into one, all dated 1
January 2021, are left out, because the Arabic articles list the same
governments one by one with usable dates.

| column | what |
|---|---|
| `person_id` | joins `persons.csv` and `layer_ministers.csv` |
| `government` | the spell id; `TN-10b` is Ghannouchi's two interim governments after 14 January 2011, `TN-18b` the weeks from 25 July 2021 in which Saïed governed without a head of government |
| `government_head`, `government_start` | the head of government and the date the government began |
| `head_of_executive` | who appointed the ministers: the president under Bourguiba, Ben Ali and, from 25 July 2021, Saïed; the head of government from 2011 to 2021 |
| `coalition` | Neo-Destour, Neo-Destour/PSD, RCD, Interim 2011 (Ghannouchi, Essebsi), Troika (Jebali, Larayedh), Technocrats (Jomaa), Nidaa-Ennahda (Essid, Chahed), Ennahda-backed (Fakhfakh, Mechichi), Presidential (Saïed's governments) |
| `era` | this repository's era of the first appointment in the government |
| `first_date`, `date_basis` | the first appointment's date where it is a day (`date`), or blank where the government stands in for it (`government`) |
| `rank_level` | the highest rank held in the government (0 head of government … 6 state secretary-general) |
| `party` | the party the sources give, French and Arabic written as one name; the first where a value records a change |
| `first_since_independence` | whether this is the person's first government from 15 April 1956 |
| `served_before_independence` | whether the person held an appointment before then |

The coalition coding follows the governments' composition in the sources and
is checked against the ministers' own `party`: Ennahda, CPR and Ettakatol
ministers sit in the Troika governments, Nidaa Tounes, Ennahda, Afek Tounes and
UPL ministers in Essid's and Chahed's.

## Results

The comparisons these files feed are made, and kept current, in EliteNetworksTN
(`docs/PAPER-elite-persistence.md` and `docs/FINDINGS-persistence.md`). This
file no longer carries their numbers, which an earlier version quoted from a
notable set the analysis has since redrawn.
