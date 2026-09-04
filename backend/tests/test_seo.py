"""Tests for the SEO endpoints (/sitemap.xml, /robots.txt)."""

import pytest

pytestmark = pytest.mark.api


def test_robots_txt(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "User-agent: *" in body
    assert "Disallow: /admin" in body
    assert "Sitemap: https://www.webbpulse.com/sitemap.xml" in body


def test_sitemap_has_static_routes(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    body = r.text
    assert body.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<loc>https://www.webbpulse.com/</loc>" in body
    assert "<loc>https://www.webbpulse.com/blog</loc>" in body
    assert "/admin" not in body


def test_sitemap_includes_published_excludes_draft(client, test_post, test_draft_post):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    body = r.text
    assert f"/blog/{test_post["slug"]}</loc>" in body
    assert f"/blog/{test_draft_post["slug"]}" not in body
