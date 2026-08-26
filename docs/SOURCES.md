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

The French edition is by far the richest for 1956–2011. Arabic adds
native-script name variants and occasionally fills post-2011 gaps.

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

This layer took education coverage from 1% to 35%, and it is what makes the
concentration of the ministerial elite in a handful of institutions visible at
all: 46 ministers passed through the Collège Sadiki and 37 through one of the
two Écoles nationales d'administration.

Gender is inferred only from unambiguous feminine grammatical forms, and only
where Wikidata supplies nothing — the masculine is French's unmarked default
and proves nothing on its own.

The same request resolves each article to its Wikidata QID via `pageprops`,
which gives a stable identifier to ministers who appear only in a roster
table and have no officeholding statement of their own.

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

- **Journal Officiel de la République Tunisienne (JORT).** The authoritative
  source: appointment decrees are published there, with exact dates. It is not
  harvested because the archive is distributed as scanned PDFs with no stable
  machine-readable index, and OCR of Arabic administrative text is a project
  in itself. **For any claim carrying argumentative weight, verify against
  JORT.** The `appointments.confidence` column exists partly to mark which
  rows most need it.
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
