"""Per-page HTML, structured data, sitemap, robots, llms.txt and Cloudflare headers.

``web/pages.json`` is the single source of truth for page metadata. Both this module (server side) and
``web/js/main.js`` (client side navigation) read it, so a title or description can never drift between them.

Design rules
- Every page is a real HTML document with its own <title>, description, canonical URL, one <h1>,
  breadcrumbs, structured data and internal links, so crawlers that do not run JavaScript still see it.
- The live API server renders the same pages but marks them ``noindex`` and emits no canonical URL
  (it is a private tool, not the public site). Only the static export is indexable.
- Structured data describes what the site honestly is (a web application and its author). It deliberately
  contains no LocalBusiness data: this is a software portfolio project, not a business with an address.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from . import __version__

CSP_STATIC = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
              "connect-src 'self'; manifest-src 'self'; worker-src 'self'; base-uri 'none'; "
              "form-action 'self'; frame-ancestors 'none'")
# <meta http-equiv> CSP cannot carry frame-ancestors (browsers log an error if it is present).
CSP_META = CSP_STATIC.replace("; frame-ancestors 'none'", "")
SOCIAL_W, SOCIAL_H = 1200, 630
_TOKEN = re.compile(r"\{\{([A-Z_]+)\}\}")


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _json_ld(obj: dict) -> str:
    # "<" is escaped so a value can never close the <script> element.
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{body}</script>'


def normalise_site_url(site_url: str | None) -> str | None:
    if not site_url:
        return None
    u = urlparse(site_url.strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ValueError(f"site url must be an absolute http(s) URL, got {site_url!r}")
    return f"{u.scheme}://{u.netloc}{u.path.rstrip('/')}"


class Site:
    """Renders pages for one deployment (a site URL for canonicals and a base path for assets)."""

    def __init__(self, web_dir: Path, site_url: str | None = None, base_path: str | None = None,
                 version: str = __version__):
        self.web_dir = Path(web_dir)
        data = json.loads((self.web_dir / "pages.json").read_text(encoding="utf-8"))
        self.meta = data["site"]
        self.pages: list[dict] = data["pages"]
        self.not_found: dict = data["not_found"]
        self.by_key = {p["key"]: p for p in self.pages}
        self.by_key["not_found"] = self.not_found
        self.by_path = {p["path"]: p for p in self.pages}
        self.template = (self.web_dir / "index.html").read_text(encoding="utf-8")
        self.site_url = normalise_site_url(site_url)
        if base_path is None:
            base_path = urlparse(self.site_url).path if self.site_url else ""
        base_path = base_path.rstrip("/")
        if base_path and not base_path.startswith("/"):
            raise ValueError("base path must start with '/'")
        self.base = base_path
        self.version = version

    # ------------------------------------------------------------------ urls
    @property
    def indexable(self) -> bool:
        return self.site_url is not None

    def href(self, page: dict) -> str:
        return f"{self.base}{page['path']}" if page["key"] != "not_found" else f"{self.base}/"

    def canonical(self, page: dict) -> str | None:
        return f"{self.site_url}{page['path']}" if self.site_url else None

    def absolute(self, rel: str) -> str:
        return f"{self.site_url}/{rel.lstrip('/')}"

    def match(self, path: str) -> dict | None:
        p = path.split("?")[0].split("#")[0]
        if p.endswith("/index.html"):
            p = p[: -len("index.html")]
        if p == "":
            p = "/"
        elif not p.endswith("/"):
            p += "/"
        return self.by_path.get(p)

    # ------------------------------------------------------------------ html fragments
    def nav_html(self, current: str | None) -> str:
        out = []
        for p in self.pages:
            cur = ' aria-current="page"' if p["key"] == current else ""
            out.append(f'<a href="{esc(self.href(p))}" data-route="{esc(p["key"])}"{cur}>{esc(p["nav"])}</a>')
        return "\n      ".join(out)

    def footer_links_html(self) -> str:
        keys = ("overview", "customers", "forecast", "assistant", "explorer", "vision")
        return "".join(f'<li><a href="{esc(self.href(self.by_key[k]))}">{esc(self.by_key[k]["crumb"])}</a></li>' for k in keys)

    def trust_links_html(self) -> str:
        keys = ("trust", "api", "about")
        return "".join(f'<li><a href="{esc(self.href(self.by_key[k]))}">{esc(self.by_key[k]["crumb"])}</a></li>' for k in keys)

    def breadcrumb_html(self, page: dict) -> str:
        if page["key"] == "overview":
            return ""
        return (f'<ol><li><a href="{esc(self.base)}/">Home</a></li>'
                f'<li aria-current="page">{esc(page["crumb"])}</li></ol>')

    def main_html(self, page: dict) -> str:
        links = "".join(
            f'<li><a href="{esc(self.href(self.by_key[k]))}">{esc(self.by_key[k]["crumb"])}</a>'
            f' <span class="muted">{esc(self.by_key[k]["description"])}</span></li>' for k in page["related"])
        return (f'<header class="page-head"><h1 id="page-title" tabindex="-1">{esc(page["h1"])}</h1>'
                f'<p class="lede">{esc(page["intro"])}</p></header>'
                f'<section class="card related"><h2>Related pages</h2><ul>{links}</ul></section>')

    def head_meta_html(self, page: dict) -> str:
        parts = []
        if not self.indexable:
            return ""
        parts.append(f'<meta name="rp-site" content="{esc(self.site_url)}">')
        canon = self.canonical(page) if page["key"] != "not_found" else None
        if canon:
            parts.append(f'<link rel="canonical" href="{esc(canon)}">')
        img = self.absolute(page["social"])
        alt = f'{self.meta["name"]}: {page["h1"]}. {self.meta["tagline"]}.'
        og = {
            "og:type": "website", "og:site_name": self.meta["name"], "og:title": page["title"],
            "og:description": page["description"], "og:locale": self.meta["locale"],
            "og:image": img, "og:image:type": "image/png", "og:image:width": str(SOCIAL_W),
            "og:image:height": str(SOCIAL_H), "og:image:alt": alt,
        }
        if canon:
            og["og:url"] = canon
        for k, v in og.items():
            parts.append(f'<meta property="{k}" content="{esc(v)}">')
        tw = {"twitter:card": "summary_large_image", "twitter:title": page["title"],
              "twitter:description": page["description"], "twitter:image": img, "twitter:image:alt": alt}
        for k, v in tw.items():
            parts.append(f'<meta name="{k}" content="{esc(v)}">')
        return "\n  ".join(parts)

    def structured_data(self, page: dict) -> list[dict]:
        if not self.indexable or page["key"] == "not_found":
            return []
        site, author = self.meta, self.meta["author"]
        root = self.site_url
        person_id = f"{root}/#author"
        website_id = f"{root}/#website"
        url = self.canonical(page)
        person = {"@type": "Person", "@id": person_id, "name": author, "url": site["author_url"],
                  "sameAs": site["same_as"]}
        graph: list[dict] = []
        if page["key"] == "overview":
            graph.append({"@type": "WebSite", "@id": website_id, "url": f"{root}/", "name": site["name"],
                          "description": site["tagline"], "inLanguage": "en", "publisher": {"@id": person_id}})
            graph.append({"@type": "WebApplication", "@id": f"{root}/#app", "name": site["name"], "url": f"{root}/",
                          "description": page["description"], "applicationCategory": "BusinessApplication",
                          "operatingSystem": "Any (web browser)", "isAccessibleForFree": True,
                          "license": "https://opensource.org/licenses/MIT", "author": {"@id": person_id},
                          "sameAs": [site["repo"]], "image": self.absolute(page["social"])})
        if page["key"] in ("overview", "about"):
            graph.append(person)
        node = {"@type": page["type"], "@id": f"{url}#webpage", "url": url, "name": page["title"],
                "description": page["description"], "inLanguage": "en", "isPartOf": {"@id": website_id},
                "primaryImageOfPage": {"@type": "ImageObject", "url": self.absolute(page["social"]),
                                       "width": SOCIAL_W, "height": SOCIAL_H}}
        if page["type"] == "TechArticle":
            node["headline"] = page["h1"]
            node["author"] = {"@id": person_id}
            graph.append(person)
        if page["key"] != "overview":
            node["breadcrumb"] = {"@id": f"{url}#breadcrumb"}
            graph.append({"@type": "BreadcrumbList", "@id": f"{url}#breadcrumb", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{root}/"},
                {"@type": "ListItem", "position": 2, "name": page["crumb"], "item": url}]})
        graph.append(node)
        # de-duplicate by @id while keeping order
        seen, uniq = set(), []
        for g in graph:
            if g["@id"] not in seen:
                seen.add(g["@id"])
                uniq.append(g)
        return uniq

    # ------------------------------------------------------------------ full page
    def render(self, page: dict) -> str:
        key = page["key"]
        current = None if key == "not_found" else key
        graph = self.structured_data(page)
        ld = _json_ld({"@context": "https://schema.org", "@graph": graph}) if graph else ""
        robots = "index, follow, max-image-preview:large" if (self.indexable and key != "not_found") else "noindex, nofollow"
        values = {
            "BASE": esc(self.base),
            "TITLE": esc(page["title"]),
            "DESCRIPTION": esc(page["description"]),
            "ROBOTS": robots,
            "HEAD_META": self.head_meta_html(page),
            "CSP_META": f'<meta http-equiv="Content-Security-Policy" content="{esc(CSP_META)}">' if self.indexable else "",
            "JSONLD": ld,
            "MODE": "static" if self.indexable else "live",
            "PAGE_KEY": esc(key),
            "VERSION": esc(self.version),
            "NAV": self.nav_html(current),
            "CRUMBS": self.breadcrumb_html(page),
            "CRUMBS_HIDDEN": "" if (key not in ("overview",)) else " hidden",
            "MAIN": self.main_html(page),
            "FOOT_PRODUCT": self.footer_links_html(),
            "FOOT_TRUST": self.trust_links_html(),
            "YEAR": str(_dt.date.today().year),
        }
        return _TOKEN.sub(lambda m: values.get(m.group(1), m.group(0)), self.template)

    # ------------------------------------------------------------------ crawler files
    def sitemap_xml(self, lastmod: str | None = None) -> str:
        lastmod = lastmod or _dt.date.today().isoformat()
        rows = "".join(f"  <url><loc>{esc(self.canonical(p))}</loc><lastmod>{lastmod}</lastmod></url>\n" for p in self.pages)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n")

    def robots_txt(self) -> str:
        return ("# RetailPulse: public portfolio demo. Everything here is synthetic data.\n"
                "User-agent: *\nAllow: /\n\n"
                f"Sitemap: {self.site_url}/sitemap.xml\n")

    def llms_txt(self) -> str:
        m = self.meta
        lines = [f"# {m['name']}", "",
                 f"> {m['tagline']}. A portfolio project by {m['author']}: SQL star-schema warehouse, forecasting, churn, "
                 "a cited RAG assistant, a guarded tool-using agent and an image classifier, behind a role-based API. "
                 "All data is synthetic (fixed seed); no real customers or business results are claimed.", "",
                 "Facts worth knowing before quoting this site: the demand model under-forecasts on its "
                 "holdout (the bias is reported on the forecast page); evaluation sets are small and self-written; the classifier is trained on synthetic icons. "
                 "The limitations page lists the rest.", "", "## Pages", ""]
        for p in self.pages:
            lines.append(f"- [{p['crumb']}]({self.canonical(p)}): {p['description']}")
        repo = m["repo"]
        lines += ["", "## Source and documentation", "",
                  f"- [Repository]({repo}): code, tests and CI",
                  f"- [README]({repo}/blob/main/README.md): overview, results table, quickstart",
                  f"- [Security model]({repo}/blob/main/SECURITY.md): threat model and known gaps",
                  f"- [Limitations]({repo}/blob/main/docs/LIMITATIONS.md): what the numbers do and do not show",
                  f"- [Architecture decisions]({repo}/blob/main/docs/ARCHITECTURE.md): why it is built this way",
                  "", "## Optional", "",
                  f"- [OpenAPI document]({self.absolute('demo/openapi.json')}): the REST API description",
                  f"- [Author]({m['author_url']}): {m['author']}", ""]
        return "\n".join(lines)

    def headers_file(self) -> str:
        """Cloudflare Pages `_headers` (also valid for Netlify). GitHub Pages ignores it."""
        return (
            "/*\n"
            "  X-Content-Type-Options: nosniff\n"
            "  X-Frame-Options: DENY\n"
            "  Referrer-Policy: strict-origin-when-cross-origin\n"
            "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()\n"
            "  Cross-Origin-Opener-Policy: same-origin\n"
            f"  Content-Security-Policy: {CSP_STATIC}\n"
            "/icons/*\n  Cache-Control: public, max-age=86400\n"
            "/samples/*\n  Cache-Control: public, max-age=86400\n"
            "/social/*\n  Cache-Control: public, max-age=86400\n"
        )
