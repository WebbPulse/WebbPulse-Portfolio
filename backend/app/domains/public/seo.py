"""The sitemap and robots documents, rendered from the published posts."""

from xml.sax.saxutils import escape

from fastapi import APIRouter
from fastapi.responses import Response

from ...config import settings
from ...db.serializer import parse_datetime
from .repository import posts

router = APIRouter()


def _lastmod(post):
    """A post's last modified date as an ISO date, or `None` when unknown."""
    value = parse_datetime(post.get("updated_at") or post.get("published_at"))
    return value.date().isoformat() if value else None


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap() -> Response:
    """An XML sitemap listing the home page, the blog index and every published post."""
    base = settings.SITE_URL.rstrip("/")
    urls = [
        {"loc": f"{base}/", "changefreq": "monthly", "priority": "1.0"},
        {"loc": f"{base}/blog", "changefreq": "weekly", "priority": "0.8"},
    ]
    for post in posts.list_published():
        urls.append(
            {
                "loc": f"{base}/blog/{post['slug']}",
                "lastmod": _lastmod(post),
                "changefreq": "monthly",
                "priority": "0.6",
            }
        )

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(url['loc'])}</loc>")
        if url.get("lastmod"):
            lines.append(f"    <lastmod>{url['lastmod']}</lastmod>")
        lines.append(f"    <changefreq>{url['changefreq']}</changefreq>")
        lines.append(f"    <priority>{url['priority']}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return Response(content="\n".join(lines) + "\n", media_type="application/xml")


@router.get("/robots.txt", include_in_schema=False)
async def robots() -> Response:
    """A robots.txt allowing everything but `/admin` and naming the sitemap."""
    base = settings.SITE_URL.rstrip("/")
    body = f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {base}/sitemap.xml\n"
    return Response(content=body, media_type="text/plain")
