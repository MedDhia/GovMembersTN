"""Cached, rate-limited HTTP with provenance recording.

Every response is written to `data/raw/<source>/` and registered in that
directory's `MANIFEST.json` with its URL, parameters, retrieval timestamp and
content hash. This is what makes the dataset auditable: any cell in the final
tables can be traced to the exact payload it came from, and a reviewer can
re-run the pipeline against the cached payloads without touching the network.

Caching is also the politeness mechanism. Re-running the build after changing
a parser costs zero requests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


class FetchError(RuntimeError):
    """Raised when a URL could not be retrieved after all retries."""


@dataclass
class Fetcher:
    """Rate-limited HTTP client scoped to one source.

    Parameters
    ----------
    source:
        Short name; becomes the `data/raw/<source>/` subdirectory.
    rate_limit:
        Minimum seconds between requests that actually hit the network.
    offline:
        When True, only cached payloads are served and a cache miss raises.
        Used by the test suite and by anyone re-building from a shipped cache.
    """

    source: str
    rate_limit: float = 1.0
    timeout: float = 60.0
    offline: bool = False
    session: requests.Session = field(default_factory=requests.Session)
    _last_request: float = field(default=0.0, init=False)
    _manifest: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.session.headers.update({"User-Agent": config.USER_AGENT})
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            with self.manifest_path.open(encoding="utf-8") as fh:
                self._manifest = json.load(fh)
        else:
            self._manifest = {"source": self.source, "entries": {}}

    # -- paths -------------------------------------------------------------

    @property
    def cache_dir(self) -> Path:
        return config.paths().raw / self.source

    @property
    def manifest_path(self) -> Path:
        return self.cache_dir / "MANIFEST.json"

    @staticmethod
    def _key(url: str, params: dict[str, Any] | None) -> str:
        payload = url + "|" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]

    # -- fetching ----------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.monotonic()

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        force: bool = False,
        binary: bool = False,
    ) -> str:
        """Fetch `url`, serving from cache unless `force`."""
        key = self._key(url, params)
        suffix = ".bin" if binary else ".txt"
        path = self.cache_dir / f"{key}{suffix}"

        if path.exists() and not force:
            return path.read_text(encoding="utf-8", errors="replace")

        if self.offline:
            raise FetchError(
                f"offline mode: no cached payload for {url} params={params}. "
                "Run the harvest with network access first, or point "
                "GOVTN_ROOT at a tree that ships data/raw/."
            )

        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._throttle()
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:      # network-level failure
                last_error = exc
                log.warning("%s attempt %d/%d failed: %s", url, attempt, MAX_ATTEMPTS, exc)
                time.sleep(2 ** attempt)
                continue

            if response.status_code in RETRY_STATUS:
                # Honour Retry-After when the server sends one; Wikimedia does.
                wait = float(response.headers.get("Retry-After", 2 ** attempt))
                log.warning(
                    "%s returned %d, retrying in %.1fs (attempt %d/%d)",
                    url, response.status_code, wait, attempt, MAX_ATTEMPTS,
                )
                last_error = FetchError(f"HTTP {response.status_code}")
                time.sleep(wait)
                continue

            response.raise_for_status()
            text = response.text
            path.write_text(text, encoding="utf-8")
            self._record(key, url, params, response, text)
            return text

        raise FetchError(f"could not fetch {url} after {MAX_ATTEMPTS} attempts") from last_error

    def get_json(self, url: str, params: dict[str, Any] | None = None, *, force: bool = False) -> Any:
        raw = self.get(url, params, force=force)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FetchError(f"{url} did not return JSON: {raw[:200]!r}") from exc

    # -- provenance --------------------------------------------------------

    def _record(self, key, url, params, response, text) -> None:
        self._manifest["entries"][key] = {
            "url": url,
            "params": params or {},
            "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": response.status_code,
            "bytes": len(text.encode("utf-8")),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "final_url": response.url,
        }
        self.flush()

    def flush(self) -> None:
        self._manifest["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tmp = self.manifest_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self._manifest, fh, indent=2, ensure_ascii=False, sort_keys=True)
        tmp.replace(self.manifest_path)

    def provenance(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Manifest entry for a URL, for attaching to extracted records."""
        return self._manifest["entries"].get(self._key(url, params), {})
