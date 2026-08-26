"""Cross-source entity resolution.

The same minister arrives from three sources under three spellings and with no
shared key: Wikidata gives a QID, Wikipedia gives an article title, Leaders
gives a French name string. This module clusters those records into stable
person identities.

STRATEGY, in decreasing order of evidence strength:

  1. Wikidata QID           - authoritative, never overridden.
  2. Wikipedia sitelink     - an article title resolved to a QID through
                              Wikidata's sitelinks is as good as a QID.
  3. Wikilink target        - two roster rows linking to the same article are
                              the same person even if the displayed names
                              differ ("Bourguiba" vs "Habib Bourguiba").
  4. Name similarity        - transliteration-invariant matching, blocked on
                              shared rare tokens and gated by the checks below.

Rule 4 is where false merges come from, so it is constrained by two
DISQUALIFIERS that veto a merge no matter how similar the names are:

  * contradictory birth years (more than one year apart), and
  * holding the same portfolio in the same cabinet under different names -
    which is evidence of two people being confused, not of one person.

A merge that only rule 4 supports is recorded with its score in the audit
trail, so borderline decisions can be reviewed rather than trusted blindly.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import config
from .normalize import clean_name, name_key, name_similarity, name_tokens_strong

log = logging.getLogger(__name__)

# A name-only merge needs strong agreement. 0.75 sits above the 0.33 that
# same-surname different-person pairs score and below the 0.9 that a genuine
# missing-middle-name pair scores (see tests/test_normalize.py).
NAME_MERGE_THRESHOLD = 0.75

# Tokens too common in Tunisian names to block on: using them would compare
# every Mohamed against every other Mohamed.
COMMON_TOKENS = {
    "mohamad", "mohamed", "muhamad", "ahmad", "ahmed", "ali", "ban", "ben",
    "abdal", "abdel", "habib", "hasan", "hassan", "husain", "hussein", "sidi",
    "mustafa", "mustapha", "salah", "taib", "tahar", "yusuf", "sad", "said",
}


class UnionFind:
    """Disjoint-set forest over record keys."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:          # path compression
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for item in self.parent:
            out[self.find(item)].append(item)
        return out


@dataclass
class SourceRecord:
    """One mention of a person in one source."""

    record_id: str
    source: str                       # "wikidata" | "wikipedia" | "leaders"
    name: str
    # Other names for the SAME person, most importantly the Arabic label.
    # Arabic and Latin spellings of one name share no tokens, so a roster row
    # harvested from the Arabic Wikipedia can never match its French
    # counterpart by name alone - the person is simply duplicated. Carrying
    # Wikidata's Arabic label as an alias on the Wikidata record bridges the
    # two scripts through the QID.
    aliases: tuple[str, ...] = ()
    qid: str | None = None
    wikilink: str | None = None
    birth_year: int | None = None
    cabinet: str | None = None
    portfolio: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens(self) -> frozenset[str]:
        """Blocking tokens from the primary name and every alias."""
        tokens = set(name_tokens_strong(self.name))
        for alias in self.aliases:
            tokens |= name_tokens_strong(alias)
        return frozenset(tokens)

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


@dataclass
class Decision:
    """An audit-trail entry for one merge."""

    left: str
    right: str
    rule: str
    score: float | None = None


class Reconciler:
    def __init__(self, threshold: float = NAME_MERGE_THRESHOLD) -> None:
        self.threshold = threshold
        self.uf = UnionFind()
        self.records: dict[str, SourceRecord] = {}
        self.decisions: list[Decision] = []
        self.rejections: list[Decision] = []
        # Per-cluster attribute sets, keyed by union-find root. The
        # disqualifiers have to be evaluated against these rather than against
        # the two records being linked: merges are TRANSITIVE, so a pairwise
        # check passes for A-B and B-C while the resulting cluster fuses A's
        # QID with C's - two different people in one row, with two careers
        # merged into one. Pairwise checking alone let four of those through.
        self.cluster_qids: dict[str, set[str]] = {}
        self.cluster_births: dict[str, set[int]] = {}

    # -- ingestion ---------------------------------------------------------

    def add(self, record: SourceRecord) -> None:
        self.records[record.record_id] = record
        self.uf.add(record.record_id)
        self.cluster_qids[record.record_id] = {record.qid} if record.qid else set()
        self.cluster_births[record.record_id] = (
            {record.birth_year} if record.birth_year else set()
        )

    def add_all(self, records: Iterable[SourceRecord]) -> None:
        for record in records:
            self.add(record)

    # -- disqualifiers -----------------------------------------------------

    def _birth_conflict(self, a: SourceRecord, b: SourceRecord) -> bool:
        """Birth years more than a year apart mean different people.

        One year of slack absorbs the common off-by-one between sources that
        record a birth year and sources that record an age.
        """
        if a.birth_year and b.birth_year:
            return abs(a.birth_year - b.birth_year) > 1
        return False

    def _same_seat_conflict(self, a: SourceRecord, b: SourceRecord) -> bool:
        """Two differently-named holders of one seat are two people.

        If both records name the same portfolio in the same cabinet but the
        names are not identical after normalisation, that is a succession or
        a source disagreement - never evidence of identity.
        """
        if not (a.cabinet and b.cabinet and a.portfolio and b.portfolio):
            return False
        if (a.cabinet, a.portfolio) != (b.cabinet, b.portfolio):
            return False
        return name_key(a.name) != name_key(b.name)

    def _blocked(self, a: SourceRecord, b: SourceRecord) -> str | None:
        if a.qid and b.qid and a.qid != b.qid:
            return "distinct_qids"
        if self._birth_conflict(a, b):
            return "birth_year_conflict"
        if self._same_seat_conflict(a, b):
            return "same_seat_different_name"
        return None

    # -- linking -----------------------------------------------------------

    def _cluster_blocked(self, a_id: str, b_id: str) -> str | None:
        """Would merging these two CLUSTERS create a contradiction?"""
        root_a, root_b = self.uf.find(a_id), self.uf.find(b_id)
        if root_a == root_b:
            return None
        qids = self.cluster_qids.get(root_a, set()) | self.cluster_qids.get(root_b, set())
        if len(qids) > 1:
            return "cluster_spans_multiple_qids"
        births = self.cluster_births.get(root_a, set()) | self.cluster_births.get(root_b, set())
        if births and max(births) - min(births) > 1:
            return "cluster_birth_year_conflict"
        return None

    def _link(self, a_id: str, b_id: str, rule: str, score: float | None = None) -> bool:
        a, b = self.records[a_id], self.records[b_id]
        reason = self._blocked(a, b) or self._cluster_blocked(a_id, b_id)
        if reason:
            self.rejections.append(Decision(a_id, b_id, reason, score))
            return False

        root_a, root_b = self.uf.find(a_id), self.uf.find(b_id)
        merged_qids = self.cluster_qids.get(root_a, set()) | self.cluster_qids.get(root_b, set())
        merged_births = (
            self.cluster_births.get(root_a, set()) | self.cluster_births.get(root_b, set())
        )
        self.uf.union(a_id, b_id)
        new_root = self.uf.find(a_id)
        self.cluster_qids[new_root] = merged_qids
        self.cluster_births[new_root] = merged_births

        self.decisions.append(Decision(a_id, b_id, rule, score))
        return True

    def link_exact_keys(self) -> None:
        """Rules 1-3: QID, resolved sitelink, and shared wikilink target."""
        for attribute, rule in (("qid", "qid"), ("wikilink", "wikilink")):
            index: dict[str, list[str]] = defaultdict(list)
            for record_id, record in self.records.items():
                value = getattr(record, attribute)
                if value:
                    index[value].append(record_id)
            for value, members in index.items():
                for other in members[1:]:
                    self._link(members[0], other, rule)

    def link_by_name(self) -> None:
        """Rule 4: blocked, scored, disqualifier-gated name matching."""
        blocks: dict[str, list[str]] = defaultdict(list)
        for record_id, record in self.records.items():
            distinctive = [t for t in record.tokens if t not in COMMON_TOKENS]
            # Fall back to common tokens only when a name is nothing else,
            # so that single-token names still get a chance to match.
            for token in (distinctive or sorted(record.tokens)):
                blocks[token].append(record_id)

        compared: set[tuple[str, str]] = set()
        for token, members in blocks.items():
            # A token shared by a very large group is not distinctive enough
            # to be worth an O(n^2) comparison inside it.
            if len(members) > 400:
                log.debug("skipping oversized block %r (%d members)", token, len(members))
                continue
            for i, left in enumerate(members):
                for right in members[i + 1:]:
                    pair = (left, right) if left < right else (right, left)
                    if pair in compared:
                        continue
                    compared.add(pair)
                    if self.uf.find(left) == self.uf.find(right):
                        continue
                    # Best match over every name/alias pair: a French roster
                    # row must be allowed to match a Wikidata record through
                    # its Latin label while an Arabic row matches the same
                    # record through its Arabic one.
                    score = max(
                        name_similarity(a, b)
                        for a in self.records[left].all_names
                        for b in self.records[right].all_names
                    )
                    if score >= self.threshold:
                        self._link(left, right, "name_similarity", round(score, 3))

    def resolve(self) -> dict[str, str]:
        """Run all rules and return record_id -> person_id."""
        self.link_exact_keys()
        self.link_by_name()

        # A cluster's identity is its QID when it has one, so that person_ids
        # stay stable across runs even as new sources are added.
        mapping: dict[str, str] = {}
        anonymous = 0
        used_slugs: dict[str, int] = {}
        # Iterate clusters in an order fixed by their contents, not by dict
        # insertion, so ids are reproducible across runs.
        clusters = sorted(
            self.uf.groups().values(), key=lambda members: sorted(members)
        )
        for members in clusters:
            qids = sorted({self.records[m].qid for m in members if self.records[m].qid})
            if qids:
                person_id = qids[0]
                if len(qids) > 1:                  # should be impossible; audit it
                    log.warning("cluster spans multiple QIDs: %s", qids)
            else:
                # Fallback id derived from the cluster's own normalised name.
                # It MUST be disambiguated: two genuinely different people can
                # share a name (and a vetoed merge guarantees two clusters with
                # identical names), and reusing the slug would silently undo
                # the veto by giving both clusters the same person_id.
                anonymous += 1
                names = sorted(clean_name(self.records[m].name) for m in members)
                slug = _slug(names[0])
                seen = used_slugs.get(slug, 0)
                used_slugs[slug] = seen + 1
                person_id = f"TN-{slug}" if not seen else f"TN-{slug}-{seen + 1}"
            for member in members:
                mapping[member] = person_id
        log.info(
            "resolved %d records into %d persons (%d without a QID); "
            "%d merges, %d vetoed",
            len(self.records), len(set(mapping.values())), anonymous,
            len(self.decisions), len(self.rejections),
        )
        return mapping

    # -- audit -------------------------------------------------------------

    def write_audit(self, path=None) -> None:
        path = path or (config.paths().ensure().interim / "reconciliation_audit.json")
        payload = {
            "threshold": self.threshold,
            "n_records": len(self.records),
            "merges": [d.__dict__ for d in self.decisions],
            "vetoed": [d.__dict__ for d in self.rejections],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, ensure_ascii=False)
        log.info("wrote reconciliation audit to %s", path)


def _slug(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "unknown"
