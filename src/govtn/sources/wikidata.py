"""Wikidata harvester.

Wikidata is the backbone of the person-level data: it is the only source that
gives structured birth dates, birthplaces, education, party affiliation and
occupation for a large share of Tunisian ministers, already reconciled to
stable identifiers (QIDs).

It is NOT sufficient on its own. Coverage of pre-1987 secretaries of state is
patchy and tenure qualifiers (P580/P582) are often missing, which is why the
Wikipedia cabinet rosters are harvested in parallel and the two are merged.

The SPARQL queries here are written to be runnable by hand in the Wikidata
Query Service UI (https://query.wikidata.org). `python -m govtn.sources.wikidata
--print-queries` dumps them, which is the fallback path when the endpoint is
unreachable from the machine running the pipeline.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Iterable, Iterator

from .. import config
from ..http import Fetcher

log = logging.getLogger(__name__)

PREFIXES = """\
PREFIX wd:  <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p:   <http://www.wikidata.org/prop/>
PREFIX ps:  <http://www.wikidata.org/prop/statement/>
PREFIX pq:  <http://www.wikidata.org/prop/qualifier/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX bd:  <http://www.bigdata.com/rdf#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
"""

LANGS = "fr,ar,en"

# ---------------------------------------------------------------------------
# Query 1 - discover the set of Tunisian government positions
# ---------------------------------------------------------------------------
# Three strategies are UNIONed rather than relying on one, because Wikidata's
# modelling of Tunisian offices is inconsistent: some ministries are typed as
# `position` with `country = Tunisia`, some only as subclasses of `minister`,
# and some are reachable only from the officeholders' side. Taking the union
# and de-duplicating is far more robust than picking one and hoping.

Q_POSITIONS = PREFIXES + """
SELECT DISTINCT ?position ?positionLabel ?positionLabelAr ?positionLabelEn
                (COUNT(DISTINCT ?holder) AS ?holders)
WHERE {
  {
    # (a) typed as a position/office whose country is Tunisia
    ?position wdt:P31/wdt:P279* wd:Q4164871 ;
              wdt:P17 wd:Q948 .
  } UNION {
    # (b) a subclass of "minister" scoped to Tunisia
    ?position wdt:P279* wd:Q83307 ;
              wdt:P17 wd:Q948 .
  } UNION {
    # (c) reached from the holder side: any position held by a Tunisian
    #     citizen where the position itself is applicable to Tunisia
    ?holder wdt:P31 wd:Q5 ; wdt:P27 wd:Q948 ; wdt:P39 ?position .
    ?position wdt:P1001 wd:Q948 .
  }
  OPTIONAL { ?holder wdt:P39 ?position . }
  OPTIONAL { ?position rdfs:label ?positionLabelAr . FILTER(LANG(?positionLabelAr) = "ar") }
  OPTIONAL { ?position rdfs:label ?positionLabelEn . FILTER(LANG(?positionLabelEn) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }
}
GROUP BY ?position ?positionLabel ?positionLabelAr ?positionLabelEn
ORDER BY DESC(?holders)
""" % LANGS

# ---------------------------------------------------------------------------
# Query 2 - officeholding statements (the appointment records)
# ---------------------------------------------------------------------------
# One row per P39 statement, carrying the tenure qualifiers. `?statement` is
# returned so a record can be traced to the exact Wikidata statement node.

Q_OFFICEHOLDERS = PREFIXES + """
SELECT ?person ?personLabel ?position ?positionLabel ?statement
       ?start ?end ?startPrecision ?endPrecision
       ?replaces ?replacesLabel ?replacedBy ?replacedByLabel ?ofLabel
WHERE {
  VALUES ?position { %s }
  ?person wdt:P31 wd:Q5 ;
          p:P39 ?statement .
  ?statement ps:P39 ?position .
  OPTIONAL { ?statement pq:P580 ?start . }
  OPTIONAL { ?statement pq:P582 ?end . }
  OPTIONAL { ?statement pq:P1365 ?replaces . }
  OPTIONAL { ?statement pq:P1366 ?replacedBy . }
  OPTIONAL { ?statement pq:P642  ?of . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }
}
""" % ("%s", LANGS)

# ---------------------------------------------------------------------------
# Query 3 - person-level attributes
# ---------------------------------------------------------------------------
# Multi-valued properties (education, occupation, party) are returned
# group-concatenated rather than as a cross product, which would otherwise
# multiply rows combinatorially and make the payload unusable.

Q_PERSONS = PREFIXES + """
SELECT ?person ?personLabel ?personLabelAr ?personLabelEn
       ?birth ?death ?birthPlace ?birthPlaceLabel ?birthRegion ?birthRegionLabel
       ?genderLabel ?countryLabel
       (GROUP_CONCAT(DISTINCT ?almaMaterLabel;  separator="|") AS ?education)
       (GROUP_CONCAT(DISTINCT ?degreeLabel;     separator="|") AS ?degrees)
       (GROUP_CONCAT(DISTINCT ?fieldLabel;      separator="|") AS ?fields)
       (GROUP_CONCAT(DISTINCT ?occupationLabel; separator="|") AS ?occupations)
       (GROUP_CONCAT(DISTINCT ?partyLabel;      separator="|") AS ?parties)
       (GROUP_CONCAT(DISTINCT ?party;           separator="|") AS ?partyQids)
       (GROUP_CONCAT(DISTINCT ?religionLabel;   separator="|") AS ?religions)
       (GROUP_CONCAT(DISTINCT ?awardLabel;      separator="|") AS ?awards)
       ?frwiki ?arwiki ?enwiki
WHERE {
  VALUES ?person { %s }
  OPTIONAL { ?person wdt:P569 ?birth . }
  OPTIONAL { ?person wdt:P570 ?death . }
  OPTIONAL {
    ?person wdt:P19 ?birthPlace .
    OPTIONAL { ?birthPlace wdt:P131 ?birthRegion . }
  }
  OPTIONAL { ?person wdt:P21  ?gender . }
  OPTIONAL { ?person wdt:P27  ?country . }
  OPTIONAL { ?person wdt:P69  ?almaMater . }
  OPTIONAL { ?person wdt:P512 ?degree . }
  OPTIONAL { ?person wdt:P101 ?field . }
  OPTIONAL { ?person wdt:P106 ?occupation . }
  OPTIONAL { ?person wdt:P102 ?party . }
  OPTIONAL { ?person wdt:P140 ?religion . }
  OPTIONAL { ?person wdt:P166 ?award . }
  OPTIONAL { ?person rdfs:label ?personLabelAr . FILTER(LANG(?personLabelAr) = "ar") }
  OPTIONAL { ?person rdfs:label ?personLabelEn . FILTER(LANG(?personLabelEn) = "en") }
  OPTIONAL { ?frwiki schema:about ?person ; schema:isPartOf <https://fr.wikipedia.org/> . }
  OPTIONAL { ?arwiki schema:about ?person ; schema:isPartOf <https://ar.wikipedia.org/> . }
  OPTIONAL { ?enwiki schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }
}
GROUP BY ?person ?personLabel ?personLabelAr ?personLabelEn ?birth ?death
         ?birthPlace ?birthPlaceLabel ?birthRegion ?birthRegionLabel
         ?genderLabel ?countryLabel ?frwiki ?arwiki ?enwiki
""" % ("%s", LANGS)


# ---------------------------------------------------------------------------
# Query 4 - multi-valued person attributes, ONE ROW PER VALUE
# ---------------------------------------------------------------------------
# Query 3 originally group-concatenated these inside the main person query.
# That silently returned empty strings for every one of them: Wikidata's
# `wikibase:label` service binds ?xLabel only for variables that survive to
# the projection, and a variable consumed by GROUP_CONCAT does not. The raw
# QIDs came through (819 people had party QIDs) while every label came back
# blank, so education, occupation, party, degrees, religion and awards were
# absent from the dataset without any error being raised.
#
# Returning one row per value and aggregating in Python avoids the
# interaction entirely, and is easier to verify.

Q_PERSON_MULTI = PREFIXES + """
SELECT ?person ?prop ?value ?valueLabel
WHERE {
  VALUES ?person { %s }
  {
    ?person wdt:P69  ?value . BIND("education"  AS ?prop)
  } UNION {
    ?person wdt:P512 ?value . BIND("degree"     AS ?prop)
  } UNION {
    ?person wdt:P101 ?value . BIND("field"      AS ?prop)
  } UNION {
    ?person wdt:P106 ?value . BIND("occupation" AS ?prop)
  } UNION {
    ?person wdt:P102 ?value . BIND("party"      AS ?prop)
  } UNION {
    ?person wdt:P140 ?value . BIND("religion"   AS ?prop)
  } UNION {
    ?person wdt:P166 ?value . BIND("award"      AS ?prop)
  } UNION {
    ?person wdt:P39  ?value . BIND("position"   AS ?prop)
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }
}
""" % ("%s", LANGS)


# Output field names, chosen to match what `govtn.build` reads. Deriving them
# by pluralising the property name gave "educations" and "partys", which the
# build then looked for under "education" and "parties" and never found.
ATTRIBUTE_FIELDS = {
    "education": "education",
    "degree": "degrees",
    "field": "fields",
    "occupation": "occupations",
    "party": "parties",
    "religion": "religions",
    "award": "awards",
    "position": "positions",
}


def harvest_person_attributes(
    person_qids: list[str], fetcher: Fetcher, *, force: bool = False
) -> dict[str, dict[str, list[str]]]:
    """Multi-valued attributes per person, aggregated in Python.

    Returns {qid: {"education": [...], "party": [...], ...}}.
    """
    chunk_size = config.sources()["wikidata"]["chunk_size"]
    out: dict[str, dict[str, list[str]]] = {}
    for batch in chunked(sorted(set(person_qids)), chunk_size):
        values = " ".join(f"wd:{q}" for q in batch)
        for row in run_query(Q_PERSON_MULTI % values, fetcher, force=force):
            person = qid(row.get("person"))
            label = (row.get("valueLabel") or "").strip()
            # An unresolved label falls back to the QID itself; that is noise,
            # not a value.
            if not person or not label or re.fullmatch(r"Q\d+", label):
                continue
            bucket = out.setdefault(person, {}).setdefault(row["prop"], [])
            if label not in bucket:
                bucket.append(label)
        log.info("attributes: %d people after %d qids", len(out), len(batch))
    return out


def _fetcher(offline: bool = False) -> Fetcher:
    cfg = config.sources()["wikidata"]
    return Fetcher(
        source="wikidata",
        rate_limit=cfg["rate_limit_seconds"],
        timeout=cfg["timeout_seconds"],
        offline=offline,
    )


def run_query(query: str, fetcher: Fetcher, *, force: bool = False) -> list[dict[str, Any]]:
    """Execute SPARQL and flatten the bindings to plain dicts.

    Wikidata returns each binding as {"value": ..., "type": ...}; only the
    value is kept, plus `<var>_datatype` for date variables so that the
    caller can distinguish a real date from a year-precision approximation.
    """
    endpoint = config.sources()["wikidata"]["sparql_endpoint"]
    payload = fetcher.get_json(
        endpoint, {"query": query, "format": "json"}, force=force
    )
    rows = []
    for binding in payload["results"]["bindings"]:
        row: dict[str, Any] = {}
        for var, cell in binding.items():
            row[var] = cell.get("value")
            if cell.get("datatype", "").endswith("#dateTime"):
                row[f"{var}_datatype"] = "dateTime"
        rows.append(row)
    return rows


def qid(uri: str | None) -> str | None:
    """http://www.wikidata.org/entity/Q123 -> Q123"""
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def chunked(items: Iterable[str], size: int) -> Iterator[list[str]]:
    batch: list[str] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def discover_positions(fetcher: Fetcher, *, force: bool = False) -> list[dict[str, Any]]:
    """All Wikidata items that look like a Tunisian government office."""
    rows = run_query(Q_POSITIONS, fetcher, force=force)
    for row in rows:
        row["position_qid"] = qid(row.get("position"))
    log.info("discovered %d candidate Tunisian government positions", len(rows))
    return rows


def harvest_officeholders(
    position_qids: list[str], fetcher: Fetcher, *, force: bool = False
) -> list[dict[str, Any]]:
    """P39 statements for the given positions, with tenure qualifiers."""
    chunk_size = config.sources()["wikidata"]["chunk_size"]
    out: list[dict[str, Any]] = []
    for batch in chunked(position_qids, chunk_size):
        values = " ".join(f"wd:{q}" for q in batch)
        rows = run_query(Q_OFFICEHOLDERS % values, fetcher, force=force)
        for row in rows:
            row["person_qid"] = qid(row.get("person"))
            row["position_qid"] = qid(row.get("position"))
        out.extend(rows)
        log.info("officeholders: %d statements after %d positions", len(out), len(batch))
    return out


def harvest_persons(
    person_qids: list[str], fetcher: Fetcher, *, force: bool = False
) -> list[dict[str, Any]]:
    """Individual-level attributes for the given people."""
    chunk_size = config.sources()["wikidata"]["chunk_size"]
    out: list[dict[str, Any]] = []
    for batch in chunked(sorted(set(person_qids)), chunk_size):
        values = " ".join(f"wd:{q}" for q in batch)
        rows = run_query(Q_PERSONS % values, fetcher, force=force)
        for row in rows:
            row["person_qid"] = qid(row.get("person"))
            row["birth_place_qid"] = qid(row.get("birthPlace"))
            row["birth_region_qid"] = qid(row.get("birthRegion"))
        out.extend(rows)
        log.info("persons: %d rows after %d qids", len(out), len(batch))
    return out


def _biography_qids() -> list[str]:
    """QIDs resolved from harvested Wikipedia biographies, if any."""
    found: list[str] = []
    for path in sorted(config.paths().interim.glob("biographies_*.json")):
        try:
            with path.open(encoding="utf-8") as fh:
                found.extend(r["qid"] for r in json.load(fh) if r.get("qid"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("could not read %s: %s", path.name, exc)
    if found:
        log.info("adding %d QIDs resolved from biography articles", len(set(found)))
    return found


def harvest(*, offline: bool = False, force: bool = False) -> dict[str, list[dict]]:
    """Full Wikidata harvest. Writes JSON to data/interim/."""
    fetcher = _fetcher(offline)
    interim = config.paths().ensure().interim

    positions = discover_positions(fetcher, force=force)
    position_qids = [p["position_qid"] for p in positions if p.get("position_qid")]

    officeholders = harvest_officeholders(position_qids, fetcher, force=force)
    person_qids = [r["person_qid"] for r in officeholders if r.get("person_qid")]

    # Also take QIDs resolved from Wikipedia biography articles. Many
    # ministers appear in a cabinet roster but have no P39 statement, so they
    # are invisible to the officeholder query - yet Wikidata still holds their
    # birth, education and party. Without this they stay attribute-less.
    person_qids.extend(_biography_qids())

    persons = harvest_persons(person_qids, fetcher, force=force)
    attributes = harvest_person_attributes(person_qids, fetcher, force=force)
    for row in persons:
        for prop, values in attributes.get(row.get("person_qid"), {}).items():
            row[ATTRIBUTE_FIELDS.get(prop, f"{prop}s")] = "|".join(values)

    bundle = {
        "positions": positions,
        "officeholders": officeholders,
        "persons": persons,
    }
    for name, rows in bundle.items():
        path = interim / f"wikidata_{name}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1, ensure_ascii=False)
        log.info("wrote %s (%d rows)", path, len(rows))
    fetcher.flush()
    return bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-queries", action="store_true",
                        help="print the SPARQL to run by hand at query.wikidata.org")
    parser.add_argument("--offline", action="store_true", help="use cached payloads only")
    parser.add_argument("--force", action="store_true", help="ignore the cache")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.print_queries:
        for name, query in [
            ("positions", Q_POSITIONS),
            ("officeholders", Q_OFFICEHOLDERS % "wd:Q1000000  # <- substitute position QIDs"),
            ("persons", Q_PERSONS % "wd:Q1000000  # <- substitute person QIDs"),
        ]:
            print(f"\n{'='*70}\n-- {name}\n{'='*70}\n{query}")
        return 0

    harvest(offline=args.offline, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
