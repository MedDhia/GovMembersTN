"""Tests for the Wikidata harvester.

The regression guarded here is the worst kind of bug this project can have:
one that returns a well-formed, complete-looking result containing nothing.
"""
import re

from govtn.sources import wikidata


def test_multivalue_query_does_not_aggregate_labels_in_sparql():
    """Labels must not be group-concatenated inside the query.

    Wikidata's `wikibase:label` service binds ?xLabel only for variables that
    survive to the projection, and a variable consumed by GROUP_CONCAT does
    not. The original person query concatenated eight label variables and got
    empty strings back for every one - education, occupation, party, degrees,
    religion and awards were simply absent from the dataset, with no error
    raised. The raw QIDs came through, which is what made it detectable.
    """
    assert "GROUP_CONCAT" not in wikidata.Q_PERSON_MULTI
    # One row per value; aggregation happens in Python.
    assert "?valueLabel" in wikidata.Q_PERSON_MULTI
    assert "wikibase:label" in wikidata.Q_PERSON_MULTI


def test_attribute_field_names_match_what_the_build_reads():
    """Deriving output names by pluralising gave "educations" and "partys".

    The build looked for "education" and "parties", found neither, and the
    recovered data was dropped a second time.
    """
    import pathlib
    build_source = (pathlib.Path(wikidata.__file__).parent.parent / "build.py").read_text()
    for field in wikidata.ATTRIBUTE_FIELDS.values():
        if field == "positions":       # harvested but not surfaced in persons.csv
            continue
        assert f'"{field}"' in build_source, f"{field} is harvested but never read"


def test_every_multivalue_property_is_named():
    properties = set(re.findall(r'BIND\("(\w+)"\s+AS \?prop\)', wikidata.Q_PERSON_MULTI))
    assert properties == set(wikidata.ATTRIBUTE_FIELDS), (
        "a property is queried but has no output field name, or vice versa"
    )


def test_unresolved_labels_are_treated_as_missing():
    # When the label service cannot resolve an item it echoes the QID. That is
    # noise, not a value, and must not land in the dataset as an institution
    # or party called "Q12345".
    source = wikidata.harvest_person_attributes.__doc__ or ""
    import inspect
    body = inspect.getsource(wikidata.harvest_person_attributes)
    assert 'fullmatch(r"Q\\d+"' in body or "fullmatch(r'Q\\d+'" in body
