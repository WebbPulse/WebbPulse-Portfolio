"""Live public system figures, cached in the public cache table and refreshed on read.

Every figure comes from a public, unauthenticated source: the latest GitHub release
of the shared packages and an up or down probe of each public product URL. The
computed set is one item, `public-figures`, in the public domain's own
`public-cache` table. A read inside
`FRESH_SECONDS` of the last refresh serves it as is. A stale read takes a short
conditional lease on that item, so one caller refreshes while the rest serve the
stale copy. Each source fails on its own: a failing source keeps its last good
figure, or is left out when it never had one. Nothing here raises to the caller.

A new source is one more `Source` in `SOURCES`.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import quote

import httpx
from botocore.exceptions import ClientError
from pydantic import BaseModel, ValidationError
from webbpulse.dynamodb import now_iso, ttl_in

from app.common.core.logging import logger
from app.common.db.client import table
from app.common.db.tables import PUBLIC_CACHE, TTL_ATTRIBUTE

CACHE_KEY = "public-figures"
"""The cache table partition key holding the cached figures and the refresh lease."""

FRESH_SECONDS = 900
"""How long a refresh is served before the next read refreshes again."""

LEASE_SECONDS = 10
"""How long one caller holds the refresh before another may take it over."""

RETAIN_SECONDS = 7 * 24 * 3600
"""The item's TTL, so last good figures outlive a quiet week but not forever."""

REFRESH_BUDGET_SECONDS = 2.5
"""The wall clock a refresh may spend on its sources before unfinished ones count as failed."""

HTTP_TIMEOUT = httpx.Timeout(2.0, connect=1.0)
"""Per request timeouts, inside the refresh budget."""

USER_AGENT = "webbpulse-portfolio-figures"
"""The User-Agent GitHub requires on API calls, also sent to the status probes."""


class Figure(BaseModel):
    """One public figure as served."""

    id: str
    label: str
    value: str
    as_of: str
    source: str
    url: Optional[str] = None


class FiguresResponse(BaseModel):
    """The figures endpoint's body."""

    figures: list[Figure]


@dataclass(frozen=True)
class Source:
    """One independently failing producer of exactly one figure, identified by `id`."""

    id: str
    fetch: Callable[[httpx.Client], Figure]


def github_release(repository: str) -> Source:
    """The latest published release of a public GitHub repository, read unauthenticated."""
    name = repository.split("/", 1)[1]
    figure_id = f"release-{name}"

    def fetch(client: httpx.Client) -> Figure:
        """Read `releases/latest` and keep only its tag and publish date."""
        response = client.get(
            f"https://api.github.com/repos/{repository}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        )
        response.raise_for_status()
        body = response.json()
        tag = str(body["tag_name"])
        return Figure(
            id=figure_id,
            label=name,
            value=tag,
            as_of=str(body["published_at"]),
            source="github",
            url=f"https://github.com/{repository}/releases/tag/{quote(tag, safe='')}",
        )

    return Source(id=figure_id, fetch=fetch)


def http_status(figure_id: str, label: str, url: str) -> Source:
    """Whether a public URL answers below 400, following redirects. A timeout is down."""

    def fetch(client: httpx.Client) -> Figure:
        """HEAD the URL, retrying as GET when HEAD is not allowed."""
        try:
            response = client.head(url, follow_redirects=True)
            if response.status_code == 405:
                response = client.get(url, follow_redirects=True)
            up = response.status_code < 400
        except httpx.HTTPError:
            up = False
        return Figure(
            id=figure_id,
            label=label,
            value="up" if up else "down",
            as_of=now_iso(),
            source="http",
            url=url,
        )

    return Source(id=figure_id, fetch=fetch)


SOURCES: tuple[Source, ...] = (
    github_release("WebbPulse/webbpulse-python"),
    github_release("WebbPulse/webbpulse-typescript"),
    github_release("WebbPulse/terraform-aws-platform-modules"),
    http_status("status-standupless", "Standupless", "https://standupless.dev"),
    http_status("status-carmodpicker", "CarModPicker", "https://www.carmodpicker.com"),
    http_status("status-portfolio", "Portfolio", "https://portfolio.webbpulse.com"),
)
"""Every source, in the order the figures are served."""


def http_client() -> httpx.Client:
    """The HTTP client one refresh shares across its sources."""
    return httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})


def _read() -> Optional[dict[str, Any]]:
    """The cached item, or `None` before the first refresh."""
    return table(PUBLIC_CACHE).get_item(Key={"pk": CACHE_KEY}).get("Item")


def _cached_figures(item: Optional[dict[str, Any]]) -> dict[str, Figure]:
    """The cached figures by id, skipping any entry that no longer validates."""
    figures: dict[str, Figure] = {}
    for entry in (item or {}).get("figures", []):
        try:
            figure = Figure(**entry)
        except (TypeError, ValidationError):
            continue
        figures[figure.id] = figure
    return figures


def _refreshed_at(item: Optional[dict[str, Any]]) -> float:
    """Epoch seconds of the last refresh, or 0 when there has been none."""
    return float((item or {}).get("refreshed_at", 0))


def _acquire_lease(now: float) -> bool:
    """Take the refresh lease, unless another caller holds it or just refreshed."""
    try:
        table(PUBLIC_CACHE).update_item(
            Key={"pk": CACHE_KEY},
            UpdateExpression="SET lease_until = :until",
            ConditionExpression=(
                "(attribute_not_exists(lease_until) OR lease_until < :now)"
                " AND (attribute_not_exists(refreshed_at) OR refreshed_at < :stale)"
            ),
            ExpressionAttributeValues={
                ":until": int(now) + LEASE_SECONDS,
                ":now": int(now),
                ":stale": int(now) - FRESH_SECONDS,
            },
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def _write(figures: list[Figure], now: float) -> None:
    """Store a refresh and release the lease."""
    table(PUBLIC_CACHE).update_item(
        Key={"pk": CACHE_KEY},
        UpdateExpression="SET figures = :figures, refreshed_at = :at, #ttl = :ttl REMOVE lease_until",
        ExpressionAttributeNames={"#ttl": TTL_ATTRIBUTE},
        ExpressionAttributeValues={
            ":figures": [figure.model_dump(exclude_none=True) for figure in figures],
            ":at": int(now),
            ":ttl": ttl_in(RETAIN_SECONDS),
        },
    )


def refresh(previous: dict[str, Figure]) -> list[Figure]:
    """Run every source in parallel inside the budget, falling back per source to `previous`."""
    fresh: dict[str, Figure] = {}
    with http_client() as client:
        executor = ThreadPoolExecutor(max_workers=len(SOURCES))
        try:
            futures = {executor.submit(source.fetch, client): source for source in SOURCES}
            done, _ = wait(futures, timeout=REFRESH_BUDGET_SECONDS)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        for future, source in futures.items():
            if future in done and future.exception() is None:
                fresh[source.id] = future.result()
                continue
            reason = repr(future.exception()) if future in done else "timed out"
            logger.warning("Figure source failed", extra={"source": source.id, "error": reason})
    ordered: list[Figure] = []
    for source in SOURCES:
        figure = fresh.get(source.id) or previous.get(source.id)
        if figure is not None:
            ordered.append(figure)
    return ordered


def current_figures(now: Optional[float] = None) -> list[Figure]:
    """The figures to serve: cached when fresh, refreshed once when stale, never raising."""
    moment = time.time() if now is None else now
    try:
        item = _read()
    except Exception as error:
        logger.warning("Figures cache read failed", extra={"error": repr(error)})
        return []
    cached = _cached_figures(item)
    fallback = [cached[source.id] for source in SOURCES if source.id in cached]
    if item is not None and _refreshed_at(item) > moment - FRESH_SECONDS:
        return fallback
    try:
        if not _acquire_lease(moment):
            return fallback
        figures = refresh(cached)
    except Exception as error:
        logger.warning("Figures refresh failed", extra={"error": repr(error)})
        return fallback
    try:
        _write(figures, moment)
    except Exception as error:
        logger.warning("Figures cache write failed", extra={"error": repr(error)})
    return figures
