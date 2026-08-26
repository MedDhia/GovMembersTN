"""govtn - a reproducible dataset of Tunisian government members, 1956-present.

The package is organised as a linear pipeline:

    sources.*   -> data/raw/       verbatim payloads from Wikidata, Wikipedia,
                                   Leaders.com.tn, with provenance manifests
    normalize   -> data/interim/   normalised names, titles, dates
    reconcile   -> data/interim/   cross-source entity resolution -> person_id
    build       -> data/processed/ analysis tables (persons, appointments, ...)
    networks    -> data/processed/ edge lists and graph files

Every stage is idempotent and writes its inputs' provenance, so any cell in the
final tables can be traced back to a source URL and a retrieval timestamp.
"""

__version__ = "0.1.0"

__all__ = ["config", "normalize", "reconcile", "build", "networks", "validate"]
