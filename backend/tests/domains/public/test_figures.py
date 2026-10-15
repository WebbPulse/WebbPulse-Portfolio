"""Tests for the live public figures endpoint and its refresh-on-read cache."""

from __future__ import annotations

import time

import httpx
import pytest

from app.common.db.client import table
from app.common.db.tables import PUBLIC_CACHE
from app.domains.public import figures

pytestmark = pytest.mark.api

RELEASES = {
    "WebbPulse/webbpulse-python": "v0.89.0",
    "WebbPulse/webbpulse-typescript": "v0.23.0",
    "WebbPulse/terraform-aws-platform-modules": "v2.40.0",
}

ALL_IDS = [source.id for source in figures.SOURCES]


class FakeUpstream:
    """A fake for every upstream the sources call, counting requests and failing on demand."""

    def __init__(self) -> None:
        """Start with every upstream healthy."""
        self.calls = 0
        self.failing: set[str] = set()
        self.down: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Answer one request as GitHub or a product site would."""
        self.calls += 1
        host = request.url.host
        if host in self.failing:
            raise httpx.ConnectError("unreachable", request=request)
        if host == "api.github.com":
            repository = request.url.path.removeprefix("/repos/").removesuffix("/releases/latest")
            if repository in self.failing:
                return httpx.Response(403, json={"message": "API rate limit exceeded"})
            return httpx.Response(
                200,
                json={"tag_name": RELEASES[repository], "published_at": "2026-10-01T00:00:00Z", "body": "x"},
            )
        if host in self.down:
            return httpx.Response(503)
        return httpx.Response(200)

    def client(self) -> httpx.Client:
        """An httpx client routed to this fake."""
        return httpx.Client(transport=httpx.MockTransport(self.handler), headers={"User-Agent": figures.USER_AGENT})


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> FakeUpstream:
    """Route every source's HTTP through a fresh fake."""
    fake = FakeUpstream()
    monkeypatch.setattr(figures, "http_client", fake.client)
    return fake


def _ids(body: dict) -> list[str]:
    """The figure ids in a response body, in order."""
    return [figure["id"] for figure in body["figures"]]


def _by_id(body: dict) -> dict[str, dict]:
    """The figures in a response body, by id."""
    return {figure["id"]: figure for figure in body["figures"]}


def _age_cache(seconds: int) -> None:
    """Move the cached refresh into the past."""
    table(PUBLIC_CACHE).update_item(
        Key={"pk": figures.CACHE_KEY},
        UpdateExpression="SET refreshed_at = :at",
        ExpressionAttributeValues={":at": int(time.time()) - seconds},
    )


def test_first_request_refreshes_every_source_and_caches(client, upstream):
    """An empty cache refreshes once, serves every figure and stores them."""
    response = client.get("/api/v1/public/figures")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    body = response.json()
    assert _ids(body) == ALL_IDS
    by_id = _by_id(body)
    assert by_id["release-webbpulse-python"] == {
        "id": "release-webbpulse-python",
        "label": "webbpulse-python",
        "value": "v0.89.0",
        "as_of": "2026-10-01T00:00:00Z",
        "source": "github",
        "url": "https://github.com/WebbPulse/webbpulse-python/releases/tag/v0.89.0",
    }
    assert by_id["status-standupless"]["value"] == "up"
    assert by_id["status-standupless"]["source"] == "http"
    assert upstream.calls == len(figures.SOURCES)

    item = table(PUBLIC_CACHE).get_item(Key={"pk": figures.CACHE_KEY})["Item"]
    assert [entry["id"] for entry in item["figures"]] == ALL_IDS
    assert "lease_until" not in item
    assert "ttl" in item


def test_a_fresh_cache_is_served_without_calling_upstream(client, upstream):
    """A second read inside the TTL is a cache hit."""
    first = client.get("/api/v1/public/figures").json()
    calls = upstream.calls

    second = client.get("/api/v1/public/figures")

    assert second.status_code == 200
    assert second.json() == first
    assert upstream.calls == calls


def test_a_stale_cache_refreshes_on_read(client, upstream):
    """Past the TTL the next read refreshes and serves the new values."""
    client.get("/api/v1/public/figures")
    _age_cache(figures.FRESH_SECONDS + 1)
    saved = dict(RELEASES)
    RELEASES["WebbPulse/webbpulse-python"] = "v0.90.0"
    upstream.down.add("standupless.dev")
    try:
        calls = upstream.calls
        body = client.get("/api/v1/public/figures").json()
    finally:
        RELEASES.clear()
        RELEASES.update(saved)

    assert upstream.calls > calls
    by_id = _by_id(body)
    assert by_id["release-webbpulse-python"]["value"] == "v0.90.0"
    assert by_id["status-standupless"]["value"] == "down"


def test_a_failing_source_keeps_its_last_good_value(client, upstream):
    """A rate limited release keeps the cached figure while the others refresh."""
    first = _by_id(client.get("/api/v1/public/figures").json())
    _age_cache(figures.FRESH_SECONDS + 1)
    upstream.failing.add("WebbPulse/webbpulse-typescript")

    body = client.get("/api/v1/public/figures")

    assert body.status_code == 200
    by_id = _by_id(body.json())
    assert _ids(body.json()) == ALL_IDS
    assert by_id["release-webbpulse-typescript"] == first["release-webbpulse-typescript"]


def test_a_failing_source_with_no_previous_value_is_left_out(client, upstream):
    """With nothing cached, a failing source is simply absent."""
    upstream.failing.add("WebbPulse/terraform-aws-platform-modules")

    body = client.get("/api/v1/public/figures").json()

    assert "release-terraform-aws-platform-modules" not in _ids(body)
    assert len(body["figures"]) == len(figures.SOURCES) - 1


def test_an_unreachable_site_reads_as_down_not_as_a_failure(client, upstream):
    """A probe that cannot connect reports the site down."""
    upstream.failing.add("www.carmodpicker.com")

    body = client.get("/api/v1/public/figures").json()

    assert _by_id(body)["status-carmodpicker"]["value"] == "down"


def test_all_sources_failing_with_an_empty_cache_is_still_a_200(client, monkeypatch, upstream):
    """Every source raising yields an empty list and a short cache lifetime, never a 5xx."""

    def broken(_client: httpx.Client) -> figures.Figure:
        """A source that always fails."""
        raise RuntimeError("upstream broke")

    monkeypatch.setattr(
        figures, "SOURCES", tuple(figures.Source(id=source.id, fetch=broken) for source in figures.SOURCES)
    )

    response = client.get("/api/v1/public/figures")

    assert response.status_code == 200
    assert response.json() == {"figures": []}
    assert response.headers["cache-control"] == "public, max-age=60"


def test_all_sources_failing_after_a_good_refresh_serves_the_last_good_set(client, monkeypatch, upstream):
    """Every source failing on a stale refresh keeps every last good figure."""
    first = client.get("/api/v1/public/figures").json()
    _age_cache(figures.FRESH_SECONDS + 1)

    def broken(_client: httpx.Client) -> figures.Figure:
        """A source that always fails."""
        raise RuntimeError("upstream broke")

    monkeypatch.setattr(
        figures, "SOURCES", tuple(figures.Source(id=source.id, fetch=broken) for source in figures.SOURCES)
    )

    response = client.get("/api/v1/public/figures")

    assert response.status_code == 200
    assert response.json() == first


def test_a_held_lease_serves_the_stale_copy_without_refreshing(client, upstream):
    """Concurrent stale readers serve the cached copy while one caller refreshes."""
    first = client.get("/api/v1/public/figures").json()
    _age_cache(figures.FRESH_SECONDS + 1)
    table(PUBLIC_CACHE).update_item(
        Key={"pk": figures.CACHE_KEY},
        UpdateExpression="SET lease_until = :until",
        ExpressionAttributeValues={":until": int(time.time()) + figures.LEASE_SECONDS},
    )
    calls = upstream.calls

    response = client.get("/api/v1/public/figures")

    assert response.json() == first
    assert upstream.calls == calls


def test_an_expired_lease_is_taken_over(client, upstream):
    """A lease left behind by a crashed refresh does not block the next one."""
    client.get("/api/v1/public/figures")
    _age_cache(figures.FRESH_SECONDS + 1)
    table(PUBLIC_CACHE).update_item(
        Key={"pk": figures.CACHE_KEY},
        UpdateExpression="SET lease_until = :until",
        ExpressionAttributeValues={":until": int(time.time()) - 1},
    )
    calls = upstream.calls

    client.get("/api/v1/public/figures")

    assert upstream.calls > calls


def test_only_one_of_two_stale_readers_takes_the_lease():
    """The conditional lease admits exactly one refresher."""
    now = time.time()

    assert figures._acquire_lease(now) is True
    assert figures._acquire_lease(now) is False


def test_a_cache_read_failure_is_a_200_with_no_figures(client, monkeypatch, upstream):
    """A broken cache table never surfaces as a server error."""

    def broken_read():
        """A cache read that fails."""
        raise RuntimeError("dynamodb unavailable")

    monkeypatch.setattr(figures, "_read", broken_read)

    response = client.get("/api/v1/public/figures")

    assert response.status_code == 200
    assert response.json() == {"figures": []}
    assert upstream.calls == 0


def test_a_cache_write_failure_still_serves_the_refresh(client, monkeypatch, upstream):
    """Figures fetched but not stored are still served."""

    def broken_write(_figures, _now):
        """A cache write that fails."""
        raise RuntimeError("dynamodb unavailable")

    monkeypatch.setattr(figures, "_write", broken_write)

    response = client.get("/api/v1/public/figures")

    assert response.status_code == 200
    assert _ids(response.json()) == ALL_IDS


def test_a_slow_source_is_cut_off_by_the_refresh_budget(client, monkeypatch, upstream):
    """A source that outlives the budget counts as failed and the rest are served."""
    monkeypatch.setattr(figures, "REFRESH_BUDGET_SECONDS", 0.2)
    slow_id = figures.SOURCES[0].id

    def slow(_client: httpx.Client) -> figures.Figure:
        """A source slower than the budget."""
        time.sleep(1)
        raise RuntimeError("too slow")

    monkeypatch.setattr(
        figures,
        "SOURCES",
        tuple(
            figures.Source(id=source.id, fetch=slow) if source.id == slow_id else source for source in figures.SOURCES
        ),
    )

    started = time.monotonic()
    body = client.get("/api/v1/public/figures").json()

    assert time.monotonic() - started < 1
    assert slow_id not in _ids(body)
    assert len(body["figures"]) == len(figures.SOURCES) - 1


def test_figures_never_carry_more_than_the_public_fields(client, upstream):
    """Only the documented fields leave the endpoint, never upstream payload extras."""
    body = client.get("/api/v1/public/figures").json()

    for figure in body["figures"]:
        assert set(figure) <= {"id", "label", "value", "as_of", "source", "url"}
