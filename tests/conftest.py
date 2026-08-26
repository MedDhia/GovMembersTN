"""Shared fixtures.

`govtn.build.run()` processes the whole harvest, which is now several thousand
records. Several tests need its output, and calling it per test made the suite
take minutes. It is deterministic for a given harvest, so build it once per
session and share the result.
"""
import pytest

from govtn import build


@pytest.fixture(scope="session")
def tables():
    """The built analysis tables, produced once for the whole test session."""
    return build.run()
