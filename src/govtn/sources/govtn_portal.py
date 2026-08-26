"""Official Tunisian government portal (tunisie.gov.tn).

The only AUTHORITATIVE source in this pipeline: the government's own listing
of its members, with the official Arabic title of each post. Everything else
here is encyclopaedic or journalistic.

Its coverage is narrow by design - it lists the CURRENT government only, with
no archive - but that is exactly the period the encyclopaedic sources are
weakest on, because a Wikipedia article for a sitting cabinet is written
slowly and is often missing entirely. It also supplies official Arabic titles
and name spellings, which anchor the Arabic-script side of entity resolution.

Only the Arabic portal is reachable; the French subdomain (fr.tunisie.gov.tn)
refuses connections, so titles arrive in Arabic and are harmonised through the
same portfolio taxonomy as every other source.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import config
from ..http import Fetcher
from ..normalize import normalize_text

log = logging.getLogger(__name__)

BASE = "https://www.tunisie.gov.tn"
MEMBERS_INDEX = "/38-%D8%A3%D8%B9%D8%B6%D8%A7%D8%A1-%D8%A7%D9%84%D8%AD%D9%83%D9%88%D9%85%D8%A9.htm"
_MEMBER_HREF = re.compile(r"/membre-de-gouvernement/\d+/")

# Honorifics that prefix every name on the portal and are not part of it.
_HONORIFIC = re.compile(r"^(السيد|السيدة|الس ي د|الأستاذ|الدكتور)\s+")

# Field labels on a member page. The portal renders them with a trailing
# colon that Arabic bidi ordering moves to the front of the visible string.
_LABELS = {
    "ministry": ("الوزارة",),
    "function": ("الوظيفة", "الخطة"),
}


def _fetcher(offline: bool = False) -> Fetcher:
    return Fetcher(source="govtn_portal", rate_limit=2.0, timeout=45, offline=offline)


def _text(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()
    return soup


def list_members(fetcher: Fetcher, *, max_pages: int = 6) -> list[str]:
    """Member page URLs from the (paginated) government members index."""
    urls: list[str] = []
    for page in range(1, max_pages + 1):
        params = {"ip": page} if page > 1 else None
        try:
            html = fetcher.get(urljoin(BASE, MEMBERS_INDEX), params)
        except Exception as exc:
            log.warning("members index page %d failed: %s", page, exc)
            break
        found = [
            urljoin(BASE, a["href"])
            for a in _text(html).find_all("a", href=True)
            if _MEMBER_HREF.search(a["href"])
        ]
        new = [u for u in dict.fromkeys(found) if u not in urls]
        if not new:
            break
        urls.extend(new)
        log.info("members index page %d: +%d (%d total)", page, len(new), len(urls))
    return urls


def parse_member(html: str, url: str) -> dict[str, Any]:
    """Name, ministry and official function from one member page."""
    soup = _text(html)
    lines = [
        line.strip()
        for line in soup.get_text("\n", strip=True).split("\n")
        if line.strip()
    ]

    record: dict[str, Any] = {"source_url": url}

    # The name is the line carrying an honorific; it is also the page heading.
    for line in lines:
        if _HONORIFIC.match(line):
            record["name"] = _HONORIFIC.sub("", line).strip()
            break

    # Labels and their values sit on consecutive lines.
    for index, line in enumerate(lines):
        stripped = line.strip(": ‏‎")
        for field, labels in _LABELS.items():
            if field in record:
                continue
            if any(stripped == label for label in labels):
                for candidate in lines[index + 1:index + 3]:
                    value = candidate.strip(": ‏‎")
                    # The portal pads some titles with tatweel (وزارة الفلاحـــة).
                    value = value.replace("ـ", "")
                    if value and not any(value == l for ls in _LABELS.values() for l in ls):
                        record[field] = re.sub(r"\s+", " ", value)
                        break
    return record


def harvest(*, offline: bool = False, max_pages: int = 6) -> list[dict[str, Any]]:
    fetcher = _fetcher(offline)
    interim = config.paths().ensure().interim

    urls = list_members(fetcher, max_pages=max_pages)
    log.info("%d government member pages", len(urls))

    records: list[dict[str, Any]] = []
    for url in urls:
        try:
            html = fetcher.get(url)
        except Exception as exc:
            log.warning("member page failed (%s): %s", url, exc)
            continue
        record = parse_member(html, url)
        if record.get("name") and (record.get("function") or record.get("ministry")):
            records.append(record)

    path = interim / "govtn_portal_members.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=1, ensure_ascii=False)
    log.info("wrote %s (%d members)", path, len(records))
    fetcher.flush()
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--max-pages", type=int, default=6)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    harvest(offline=args.offline, max_pages=args.max_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
