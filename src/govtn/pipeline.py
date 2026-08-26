"""End-to-end pipeline runner.

    python -m govtn.pipeline            # harvest everything, then build
    python -m govtn.pipeline --no-fetch # rebuild from cached payloads only

The harvest stages are independent and failure-tolerant: if Wikidata is
unreachable, the Wikipedia and Leaders stages still run and the build proceeds
with what was collected, flagging the gap in MANIFEST.json. That is deliberate
- a partial dataset that says so is more useful than a pipeline that refuses
to produce anything.
"""

from __future__ import annotations

import argparse
import logging

from . import build, config, networks, validate
from .sources import (biographies, govtn_portal, jort, leaders, wikidata,
                      wikipedia)

log = logging.getLogger(__name__)

STAGES = {
    "wikidata": lambda offline: wikidata.harvest(offline=offline),
    "wikipedia": lambda offline: wikipedia.harvest(offline=offline, langs=("fr", "ar")),
    "leaders": lambda offline: leaders.harvest(offline=offline),
    "biographies": lambda offline: biographies.harvest(offline=offline, lang="fr"),
    "govtn_portal": lambda offline: govtn_portal.harvest(offline=offline),
    "jort": lambda offline: jort.harvest(offline=offline),
}


def harvest(stages: list[str], *, offline: bool) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for stage in stages:
        log.info("=== harvest: %s ===", stage)
        try:
            STAGES[stage](offline)
            results[stage] = True
        except Exception as exc:
            log.error("harvest stage %r failed: %s", stage, exc, exc_info=True)
            results[stage] = False
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", default="wikidata,wikipedia,biographies,leaders,govtn_portal,jort",
                        help="comma-separated harvest stages, or 'none'")
    parser.add_argument("--no-fetch", action="store_true",
                        help="rebuild from cached payloads without network access")
    parser.add_argument("--skip-harvest", action="store_true",
                        help="go straight to build/networks/validate")
    parser.add_argument("--snapshot", default=None,
                        help="censoring date for open tenures (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.snapshot:
        import os
        os.environ["GOVTN_SNAPSHOT"] = args.snapshot

    config.paths().ensure()

    if not args.skip_harvest and args.stages != "none":
        results = harvest(args.stages.split(","), offline=args.no_fetch)
        failed = [s for s, ok in results.items() if not ok]
        if failed:
            log.warning("harvest incomplete - failed stages: %s", ", ".join(failed))

    log.info("=== build ===")
    build.run()
    log.info("=== networks ===")
    networks.run()
    log.info("=== validate ===")
    return validate.run()


if __name__ == "__main__":
    raise SystemExit(main())
