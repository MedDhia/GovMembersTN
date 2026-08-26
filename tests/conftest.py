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
