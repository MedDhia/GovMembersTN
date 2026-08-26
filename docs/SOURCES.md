# Sources

## Wikidata

- **Endpoint:** `https://query.wikidata.org/sparql`
- **Licence:** CC0
- **What it contributes:** stable identifiers (QIDs), birth and death dates,
  birthplace with its administrative unit, gender, education, occupation,
  party, and officeholding statements (`P39`) with tenure qualifiers
  (`P580`/`P582`).
- **Strengths:** already reconciled to identifiers, so it anchors entity
  resolution; the only source with structured birthplace-to-governorate links.
- **Weaknesses:** thin coverage of pre-1987 secretaries of state; tenure
  qualifiers frequently absent, which is why those rows carry
  `confidence = low`; party affiliation carries no dates.

**A trap worth knowing about.** Multi-valued attributes must NOT be
group-concatenated inside the SPARQL query. Wikidata's `wikibase:label`
service binds `?xLabel` only for variables that survive to the projection, and
a variable consumed by `GROUP_CONCAT` does not — so the query returns empty
strings for every label, with no error. This silently cost the dataset its
education, occupation, party, degree, religion and award data; the raw QIDs
came through, which is what made it detectable. `Q_PERSON_MULTI` returns one
row per value and aggregates in Python instead.

Tunisian ministerial offices are modelled inconsistently on Wikidata — some
are typed as positions with `country = Tunisia`, some only as subclasses of
*minister*, some are reachable only from the officeholder side. The harvester
UNIONs three discovery strategies rather than relying on any one. Run
`make queries` to get the SPARQL for manual execution.

## Wikipedia (French, Arabic, English)

- **Endpoint:** the MediaWiki API of each edition
- **Licence:** CC BY-SA 4.0
- **What it contributes:** the full ministerial rosters. This is the only
  source with near-complete cabinet composition back to 1956.

The French edition is by far the richest for 1956–2011. Arabic is not merely
a supplement: several governments have an Arabic article and **no French
one**, including the three most recent (Hachani, Madouri, Zaafarani). Each
edition therefore declares its own index in `config/sources.yml` — the Arabic
category is `تصنيف:مجالس وزراء تونس`, which is not a translation of the French
one — and non-French discovery takes the **union** of langlinks and that local
index. Treating the local index as a fallback that ran only when langlinks
returned nothing left those three governments with no ministers at all.

Cabinet articles are discovered through **both** the navigation template
`Modèle:Palette Gouvernements de la Tunisie` **and** `Catégorie:Gouvernement
de la Tunisie`, because each misses articles the other catches. The curated
spine's `wikipedia_fr` seeds are a third fallback.

Articles are fetched as **wikitext, not rendered HTML**, so that `[[wikilink]]`
targets survive — those targets resolve to QIDs through sitelinks and are a
far more reliable join than displayed name strings.

Two roster layouts occur and both are parsed: wikitables (with varying column
headers) and bullet lists of the form `* Ministre de X : [[Y]]`, which is the
usual layout for the 1950s–60s governments.

## Wikipedia biographies (categories)

Separate from the cabinet rosters, each officeholder's own article is
harvested for its **categories**. French Wikipedia uses a controlled,
regular category vocabulary that is far more reliable than parsing prose:

    Catégorie:Naissance en août 1955             -> birth, month precision
    Catégorie:Naissance à Médenine               -> birthplace
    Catégorie:Élève du Collège Sadiki            -> education
    Catégorie:Personnalité du Mouvement Ennahdha -> party
    Catégorie:Prisonnier politique tunisien      -> political imprisonment
    Catégorie:Ingénieure tunisienne              -> profession, and gender via
                                                    the feminine form

Arabic uses its own conventions and carries its own trap: the birth year is
tagged **twice**, Gregorian and Hijri — `مواليد 1955` alongside
`مواليد 1374 هـ`. Matching the year without excluding the Hijri marker puts
the birth 580 years adrift, and the result looks entirely plausible in a
table. Arabic also marks the feminine with a distinct plural (`وزيرات`,
`مهندسات`), which is an unambiguous gender signal where the masculine is not.

Orthographic folding (ة → ه, أ → ا) is used for **matching only**; values are
taken from the original category name, or every Arabic value in the dataset
would be stored folded.

This layer took education coverage from 1% to 37%, and it is what makes the
concentration of the ministerial elite in a handful of institutions visible at
all: 46 ministers passed through the Collège Sadiki and 37 through one of the
two Écoles nationales d'administration.

Gender is inferred only from unambiguous feminine grammatical forms, and only
where Wikidata supplies nothing — the masculine is French's unmarked default
and proves nothing on its own.

The same request resolves each article to its Wikidata QID via `pageprops`,
which gives a stable identifier to ministers who appear only in a roster
table and have no officeholding statement of their own.

## Journal Officiel (jort.tn)

- **Base:** `https://jort.tn`
- **Coverage:** the gazette from **1957 to the present**, French and Arabic —
  the whole span of this dataset — with OCR'd full-text search.
- **What it contributes:** the authoritative record. A ministerial appointment
  takes legal effect through a decree published in the JORT, so this is the
  only source here that can establish an appointment officially rather than
  encyclopaedically.

An earlier version of this file said the JORT was not harvested because it is
distributed as scanned PDFs with no machine-readable index. That was true of
the government's own portals (`jort.gov.tn`, `iort.gov.tn`), which refuse
connections in any case. `jort.tn` indexes the same gazette and is searchable.

**What is used, and what deliberately is not.** Full documents sit behind a
login. This harvester uses only what the site serves publicly: the search
index, result snippets, and each issue's metadata page, which carries the
publication date and the summary of decrees. It never requests the gated PDFs
and never attempts to authenticate.

**Search by decree language, not by person.** Searching per person was the
obvious approach and the wrong one: it surfaces every gazette mention of a
name — a committee presidency, a board seat, a namesake in a promotion list —
and cabinet appointments are a small minority. Searching for the appointment
language itself (`"est nommé chef du gouvernement"`,
`"sont nommés membres du gouvernement"`, `"تسمية أعضاء الحكومة"`,
`"il est mis fin aux fonctions"`) returns the decrees themselves, and the
officeholder's name can be read off the snippet. It is also two orders of
magnitude cheaper: a dozen queries rather than one per person.

**Publication is not appointment.** `jort_date` is normally when the decree
appeared in the gazette, which trails the appointment by a few days — a median
of 8 in this data. It is an authoritative upper bound on the start date, not a
replacement for it, and the difference is recorded in `jort_date_delta` rather
than silently resolved. A large gap between the harvested date and the
official record is a finding worth inspecting.

Decrees often state their own effective date (`à compter du 23 avril 1980`),
which is the appointment's actual legal date and is preferred where present —
`jort_date_kind` records which of the two a row carries. In practice it is
rare: the search snippet runs to a median of 72 characters, enough for the
officeholder's name **or** the effective date but seldom both, so only 1 of
372 decrees yields one. Reading it reliably would need the full document,
which is behind the login.

**Precision over volume.** Broad cessation queries return mostly *délégués* —
sub-national administrators, not ministers — and dominate the results:
unfiltered, they made up 779 of 1,169 decrees while yielding a single usable
name. Narrowing to ministerial phrasing cut the corpus to 372 and raised the
share with an identifiable officeholder from 18% to 57%.

Two traps are handled: `"ministre plénipotentiaire"` is a diplomatic rank
rather than a seat in cabinet and dominates the `"est nommé ministre"`
results; and issues are dated in both calendars
(`26 chaâbane 1442 – 8 avril 2021`), so only the Gregorian half is taken.

## Official government portal (tunisie.gov.tn)

- **Base:** `https://www.tunisie.gov.tn`
- **What it contributes:** the membership of the SITTING government, with each
  post's official Arabic title.

The only authoritative source in this pipeline; everything else is
encyclopaedic or journalistic. Its coverage is deliberately narrow - the
portal lists the current government and keeps no archive - but that is exactly
the period the encyclopaedic sources are weakest on, because an article for a
sitting cabinet is written slowly and is sometimes absent altogether. Before
this source was added the current government contributed one person to the
dataset, its head; it now contributes 31.

Membership is authoritative, the dates are not: the portal is a snapshot with
no appointment dates, so these rows inherit the government's start date and
carry `date_basis = cabinet`.

Only the Arabic portal is reachable. The French subdomain
(`fr.tunisie.gov.tn`) refuses connections, so titles arrive in Arabic and are
harmonised through the same portfolio taxonomy as every other source.

## Leaders.com.tn

- **Base:** `https://www.leaders.com.tn`
- **Sections:** `/categorie/who-s-who` (long-form profiles),
  `/annuaire-personnalite` (structured directory)
- **Licence:** © Leaders, all rights reserved
- **What it contributes:** education and pre-ministerial career — the single
  biggest gap in the structured sources. Wikidata records that someone was
  interior minister; Leaders records that he was a Kasserine magistrate first,
  which is what distinguishes a technocrat from a party cadre from a security
  professional.

**Copyright handling.** The harvester stores only extracted structured fields,
a short excerpt around each extraction for verification, and the source URL.
Article bodies are never retained. This is controlled by `store_full_text:
false` in `config/sources.yml`; leaving it false is what keeps the repository
redistributable.

## Politeness

`config/sources.yml` sets deliberately conservative rate limits (1–2 s between
requests). Wikimedia's User-Agent policy requires a descriptive agent with
contact information for automated access; `govtn.config.USER_AGENT` supplies
one. Every payload is cached under `data/raw/`, so re-running the build after
a parser change costs no requests at all.

## Sources deliberately not used

- **Government press releases / `pm.gov.tn`.** Good for the current cabinet,
  no historical depth, and the site has been restructured repeatedly.
- **Secondary academic datasets** on Arab ministerial elites. Useful for
  validation, but their licensing generally does not permit redistribution.

## Verifying a row

Every row in `appointments.csv` carries `source` and `source_ref`. For a
Wikipedia row, `source_ref` is the article URL and `raw_title` is the verbatim
string that was parsed. For a Wikidata row, `source_ref` is the statement URI.
`data/raw/*/MANIFEST.json` records the retrieval timestamp and content hash of
every payload, so a reviewer can confirm what the source said when it was read.
