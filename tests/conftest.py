"""Shared fixtures.

`govtn.build.run()` processes the whole harvest, which is several thousand
records. Several tests need its output, and calling it per test made the suite
take minutes, so it is built once per session and shared.

It is built into a TEMPORARY directory. Writing into `data/processed/` would
mean every `pytest` run rewrote the published tables and left the repository
dirty with a changed `generated_utc` timestamp — spurious diffs that invite
people to commit noise, and a test suite that mutates the artefact it is
supposed to be checking.

Tests that verify the PUBLISHED files (`tests/test_docs.py`) still read
`data/processed/` directly, which is the point of those checks.
"""
import pytest

from govtn import build


@pytest.fixture(scope="session")
def tables(tmp_path_factory):
    """The built analysis tables, produced once per session in a temp dir."""
    out = tmp_path_factory.mktemp("processed")
    return build.run(out_dir=out)


@pytest.fixture(scope="session")
def harvested(tables):
    """`tables`, but only where a real harvest stands behind them.

    A clone ships `data/processed/` and not the payloads under `data/raw/` and
    `data/interim/`, so on a fresh checkout `build.run()` legitimately falls
    back to the curated spine: 23 records, one per government. Most tests are
    structural and hold on that. A handful assert magnitudes that only a real
    harvest can produce - hundreds of coded birthplaces, enough coded
    ministers per era for the representation index to report at all - and
    those failed on every fresh clone, which made `make test` look broken to
    anyone who had not harvested first.

    Depend on this fixture instead of `tables` when a test needs the volume
    rather than the shape.
    """
    if not any(build._source_status().values()):
        pytest.skip(
            "no harvested payloads under data/interim/ - build.run() fell back "
            "to the 23-row curated spine, and this test asserts magnitudes only "
            "a real harvest produces. Run `make all` (network) or `make offline` "
            "(from cached payloads) first.")
    return tables
