"""Check that every source host this pipeline needs is actually reachable.

Run this BEFORE `make all`. A harvest against a blocked host does not fail
loudly - each stage catches its own errors so that one dead source does not
sink the others - so it can quietly produce empty tables. This check makes the
network state explicit first.

    make preflight

Exits 0 when every required host answers, 1 otherwise, and names what to
allowlist for the ones that do not.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests

from . import config

# Domains to allowlist, in the form an egress policy usually wants them.
REQUIRED_DOMAINS = [
    ("*.wikipedia.org", "cabinet rosters (fr, ar, en editions)"),
    ("query.wikidata.org", "SPARQL endpoint for officeholders and attributes"),
    ("www.wikidata.org", "Wikidata entity API"),
    ("www.leaders.com.tn", "biographies: education and pre-ministerial career"),
]


@dataclass
class Check:
    name: str
    url: str
    params: dict | None
    purpose: str
    required: bool = True

    ok: bool = False
    detail: str = ""

    def run(self, timeout: float = 20.0) -> "Check":
        try:
            response = requests.get(
                self.url, params=self.params, timeout=timeout,
                headers={"User-Agent": config.USER_AGENT},
            )
        except requests.exceptions.ProxyError as exc:
            # The agent proxy answers 403 to CONNECT for a host outside the
            # environment's egress policy. This is the case that matters here.
            self.detail = f"blocked by the egress proxy ({_short(exc)})"
        except requests.exceptions.SSLError as exc:
            self.detail = (
                f"TLS verification failed ({_short(exc)}). Point the client at "
                "the proxy CA bundle rather than disabling verification."
            )
        except (requests.exceptions.ConnectionError, socket.gaierror) as exc:
            self.detail = f"could not connect ({_short(exc)})"
        except requests.exceptions.Timeout:
            self.detail = f"timed out after {timeout:.0f}s"
        except requests.RequestException as exc:
            self.detail = _short(exc)
        else:
            if response.status_code in (403, 407):
                self.detail = (
                    f"HTTP {response.status_code} - refused by a proxy or by the "
                    "host. If this is the egress proxy, the domain needs "
                    "allowlisting; do not retry."
                )
            elif response.status_code >= 400:
                self.detail = f"HTTP {response.status_code}"
            else:
                self.ok = True
                self.detail = f"HTTP {response.status_code}, {len(response.content)} bytes"
        return self


def _short(exc: Exception, limit: int = 90) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= limit else text[:limit] + "..."


def build_checks() -> list[Check]:
    """One minimal, real request per source - not a bare connectivity ping.

    Each check exercises the same endpoint and query shape the harvester uses,
    so a pass here means the harvest can actually run, not merely that DNS
    resolves.
    """
    sources = config.sources()
    checks: list[Check] = [
        Check(
            name="wikidata (SPARQL)",
            url=sources["wikidata"]["sparql_endpoint"],
            params={"query": "SELECT ?x WHERE { wd:Q948 rdfs:label ?x } LIMIT 1",
                    "format": "json"},
            purpose="officeholding statements and person attributes",
        ),
        Check(
            name="wikidata (entity API)",
            url=sources["wikidata"]["entity_api"],
            params={"action": "wbgetentities", "ids": "Q948",
                    "props": "labels", "languages": "en", "format": "json"},
            purpose="entity lookups",
        ),
    ]
    for edition in sources["wikipedia"]["editions"]:
        checks.append(Check(
            name=f"wikipedia ({edition['lang']})",
            url=edition["api"],
            params={"action": "query", "meta": "siteinfo", "format": "json"},
            purpose="cabinet rosters",
            # Only French is load-bearing; ar/en add name variants and gap-fill.
            required=edition["lang"] == "fr",
        ))
    checks.append(Check(
        name="leaders.com.tn",
        url=sources["leaders"]["base_url"],
        params=None,
        purpose="education and pre-ministerial career",
        required=False,
    ))
    return checks


def run(*, as_json: bool = False) -> int:
    checks = [check.run() for check in build_checks()]
    failed_required = [c for c in checks if c.required and not c.ok]
    failed_optional = [c for c in checks if not c.required and not c.ok]

    if as_json:
        print(json.dumps([
            {"name": c.name, "ok": c.ok, "required": c.required,
             "host": urlsplit(c.url).netloc, "detail": c.detail}
            for c in checks
        ], indent=2))
        return 1 if failed_required else 0

    print("Source reachability\n" + "-" * 72)
    for check in checks:
        mark = "PASS" if check.ok else ("FAIL" if check.required else "warn")
        tag = "" if check.required else "  (optional)"
        print(f"  [{mark}] {check.name:22s} {check.detail}{tag}")

    print()
    if not failed_required and not failed_optional:
        print("All sources reachable. Run `make all` to harvest and build.")
        return 0

    if failed_required:
        print("REQUIRED SOURCES UNREACHABLE - the harvest cannot produce a full")
        print("dataset until these are allowlisted for this environment:\n")
    else:
        print("Optional sources unreachable. The harvest will run and will flag")
        print("the gap in data/processed/MANIFEST.json:\n")

    blocked_hosts = {urlsplit(c.url).netloc for c in failed_required + failed_optional}
    for domain, purpose in REQUIRED_DOMAINS:
        suffix = domain.lstrip("*.")
        if any(host.endswith(suffix) for host in blocked_hosts):
            print(f"    {domain:24s} {purpose}")

    print(
        "\nThese are set by the environment's network policy, not by this repo.\n"
        "An admin can widen it in the Claude Code environment settings on\n"
        "claude.ai; see https://code.claude.com/docs/en/claude-code-on-the-web.\n"
        "Re-run `make preflight` afterwards to confirm before harvesting.\n"
        "\nIf only Wikidata stays blocked, `make queries` prints the SPARQL to\n"
        "run by hand at https://query.wikidata.org and save into data/interim/.\n"
        "\nMeanwhile `make build` still assembles the tables from the curated\n"
        "seed, and `make offline` rebuilds everything from any cached payloads\n"
        "under data/raw/. Both flag the partial harvest in MANIFEST.json."
    )
    return 1 if failed_required else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    return run(as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
