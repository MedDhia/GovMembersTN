"""Configuration and path resolution.

Paths are resolved relative to the repository root so that scripts work from
any working directory. Config files are read once and cached.
"""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    """Repository root, overridable with GOVTN_ROOT for tests and CI."""
    env = os.environ.get("GOVTN_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def interim(self) -> Path:
        return self.root / "data" / "interim"

    @property
    def processed(self) -> Path:
        """Analysis-ready tables: the five core CSVs a user actually loads."""
        return self.root / "data" / "processed"

    @property
    def networks(self) -> Path:
        """Edge lists and graph files, kept out of the core table listing.

        Someone opening `data/processed/` should see the tables they are meant
        to load, not four core tables buried among eight network exports.
        """
        return self.processed / "networks"

    @property
    def indices(self) -> Path:
        """Derived measures computed FROM the core tables, not alongside them.

        Keeping them separate marks the dependency: these can be regenerated
        from the tables, the tables cannot be regenerated from these.
        """
        return self.processed / "indices"

    def ensure(self) -> "Paths":
        for p in (self.raw, self.interim, self.processed,
                  self.networks, self.indices):
            p.mkdir(parents=True, exist_ok=True)
        return self


def paths() -> Paths:
    return Paths(repo_root())


@functools.lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    """Load `config/<name>.yml`."""
    path = paths().config / f"{name}.yml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def cabinets() -> dict[str, Any]:
    return load_yaml("cabinets")


def portfolios() -> dict[str, Any]:
    return load_yaml("portfolios")


def sources() -> dict[str, Any]:
    return load_yaml("sources")


# --- snapshot date ---------------------------------------------------------
# Open-ended tenures (`end: null`) need a censoring date for any duration
# calculation. Freezing it in the manifest is what makes tenure lengths
# reproducible: re-running the pipeline a year later must not silently
# lengthen every incumbent's tenure in an already-published table.

def snapshot_date() -> date:
    """Censoring date for open-ended tenures.

    Reads GOVTN_SNAPSHOT (YYYY-MM-DD) if set, else the manifest, else today.
    """
    env = os.environ.get("GOVTN_SNAPSHOT")
    if env:
        return date.fromisoformat(env)
    manifest = paths().processed / "MANIFEST.json"
    if manifest.exists():
        with manifest.open(encoding="utf-8") as fh:
            recorded = json.load(fh).get("snapshot_date")
        if recorded:
            return date.fromisoformat(recorded)
    return datetime.now(timezone.utc).date()


USER_AGENT = (
    "GovMembersTN/0.1 (https://github.com/MedDhia/GovMembersTN; "
    "academic research on Tunisian ministerial elites) python-requests"
)
