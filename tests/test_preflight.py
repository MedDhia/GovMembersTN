"""Tests for the preflight reachability check.

These must not touch the network themselves, so `requests.get` is replaced.
What is being tested is the diagnosis: a blocked host has to be reported as
blocked and named in the allowlist hint, not swallowed into a generic error.
"""
import requests

from govtn import preflight


def test_checks_cover_every_configured_source():
    checks = preflight.build_checks()
    names = {c.name for c in checks}
    assert "wikidata (SPARQL)" in names
    assert "wikipedia (fr)" in names
    assert "leaders.com.tn" in names
    # Only the French Wikipedia and Wikidata are load-bearing; the rest add
    # name variants and gap-fill, so a missing one must not fail the run.
    required = {c.name for c in checks if c.required}
    assert "wikipedia (fr)" in required
    assert "wikipedia (ar)" not in required
    assert "leaders.com.tn" not in required


def test_each_check_exercises_a_real_query_not_a_bare_ping():
    # A check that only confirms DNS would pass against a host that refuses
    # the actual API call.
    by_name = {c.name: c for c in preflight.build_checks()}
    assert by_name["wikidata (SPARQL)"].params["query"].startswith("SELECT")
    assert by_name["wikipedia (fr)"].params["action"] == "query"


def test_proxy_block_is_diagnosed_as_a_block(monkeypatch):
    def blocked(*args, **kwargs):
        raise requests.exceptions.ProxyError("gateway answered 403 to CONNECT")

    monkeypatch.setattr(preflight.requests, "get", blocked)
    check = preflight.build_checks()[0].run(timeout=1)
    assert not check.ok
    assert "blocked by the egress proxy" in check.detail


def test_http_403_is_not_reported_as_success(monkeypatch):
    class Response:
        status_code = 403
        content = b""

    monkeypatch.setattr(preflight.requests, "get", lambda *a, **k: Response())
    check = preflight.build_checks()[0].run(timeout=1)
    assert not check.ok
    assert "403" in check.detail and "allowlisting" in check.detail


def test_success_is_reported(monkeypatch):
    class Response:
        status_code = 200
        content = b'{"ok": true}'

    monkeypatch.setattr(preflight.requests, "get", lambda *a, **k: Response())
    checks = [c.run(timeout=1) for c in preflight.build_checks()]
    assert all(c.ok for c in checks)


def test_exit_code_ignores_optional_sources(monkeypatch, capsys):
    def selective(url, **kwargs):
        class Response:
            content = b"{}"
            status_code = 200 if "leaders" not in url else 403
        return Response()

    monkeypatch.setattr(preflight.requests, "get", selective)
    assert preflight.run() == 0, "an optional source must not fail preflight"
    assert "optional" in capsys.readouterr().out


def test_failure_names_the_domains_to_allowlist(monkeypatch, capsys):
    monkeypatch.setattr(
        preflight.requests, "get",
        lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ProxyError("403")),
    )
    assert preflight.run() == 1
    out = capsys.readouterr().out
    assert "*.wikipedia.org" in out and "query.wikidata.org" in out
    # And it must point at the fallbacks rather than leaving the user stuck.
    assert "make build" in out and "make queries" in out
