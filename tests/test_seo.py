"""SEO, slugs, 404, structured data and crawler files for the static site and the live server."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest
from PIL import Image

from retailpulse import export_static
from retailpulse.api import create_app
from retailpulse.security import ApiKeyStore, RateLimiter
from retailpulse.seo import Site

from .asgi_client import request

WEB = Path(__file__).resolve().parent.parent / "web"
URL = "https://example.test"
PAGES = json.loads((WEB / "pages.json").read_text())["pages"]
BAD_WORDS = re.compile(r"react|vite|untitled|lorem|placeholder|localhost|index\.html|new tab", re.I)


class Doc(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.h1, self.imgs, self.links, self.meta, self.ld = [], [], [], {}, []
        self.title, self.canonical, self._in, self._buf, self._ld = "", None, None, "", False
        self.feed(text)

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag in ("h1", "title"):
            self._in, self._buf = tag, ""
        elif tag == "img":
            self.imgs.append(a)
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "meta":
            key = a.get("name") or a.get("property") or a.get("http-equiv")
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld, self._buf = True, ""

    def handle_data(self, d):
        if self._in or self._ld:
            self._buf += d

    def handle_endtag(self, tag):
        if tag == self._in:
            (self.h1.append if tag == "h1" else lambda s: setattr(self, "title", s))(self._buf.strip())
            self._in = None
        elif tag == "script" and self._ld:
            self.ld.append(json.loads(self._buf))
            self._ld = False


@pytest.fixture(scope="module")
def site(tmp_path_factory, built):
    out = tmp_path_factory.mktemp("seo") / "site"
    export_static.export(out, paths=built[0], site_url=URL)
    return out


def page_file(site, p):
    return site / ("index.html" if p["path"] == "/" else p["path"].strip("/") + "/index.html")


def docs(site):
    return {p["key"]: Doc(page_file(site, p).read_text()) for p in PAGES}


def test_each_slug_is_a_real_file_with_unique_title_description_and_one_h1(site):
    d = docs(site)
    titles = [x.title for x in d.values()]
    assert len(set(titles)) == len(titles) == len(PAGES)
    assert len({x.meta["description"] for x in d.values()}) == len(PAGES)
    for p in PAGES:
        x = d[p["key"]]
        assert x.title == p["title"] and 20 <= len(x.title) <= 60, x.title
        assert 70 <= len(x.meta["description"]) <= 170
        assert len(x.h1) == 1 and x.h1[0] == p["h1"]
        assert not BAD_WORDS.search(x.title) and not BAD_WORDS.search(x.meta["description"])
        assert x.meta["robots"].startswith("index")


def test_canonical_open_graph_twitter_and_sitemap_agree(site):
    sm = set(re.findall(r"<loc>(.*?)</loc>", (site / "sitemap.xml").read_text()))
    assert sm == {URL + p["path"] for p in PAGES}
    for p in PAGES:
        x = Doc(page_file(site, p).read_text())
        want = URL + p["path"]
        assert x.canonical == want and x.meta["og:url"] == want
        assert x.meta["og:title"] == x.title and x.meta["twitter:card"] == "summary_large_image"
        assert x.meta["og:image"] == f"{URL}/{p['social']}" and x.meta["og:image:alt"]
        img = Image.open(site / p["social"])
        assert img.size == (1200, 630) and img.format == "PNG"


def test_structured_data_is_valid_honest_and_has_breadcrumbs(site):
    allld = ""
    for p in PAGES:
        x = Doc(page_file(site, p).read_text())
        assert len(x.ld) == 1 and x.ld[0]["@context"] == "https://schema.org"
        nodes = x.ld[0]["@graph"]
        types = {n["@type"] for n in nodes}
        assert p["type"] in types
        ids = [n["@id"] for n in nodes]
        assert len(ids) == len(set(ids))
        if p["key"] == "overview":
            assert {"WebSite", "WebApplication", "Person"} <= types and "BreadcrumbList" not in types
        else:
            crumbs = next(n for n in nodes if n["@type"] == "BreadcrumbList")
            assert [i["position"] for i in crumbs["itemListElement"]] == [1, 2]
            assert crumbs["itemListElement"][1]["item"] == URL + p["path"]
        allld += json.dumps(x.ld)
    assert "LocalBusiness" not in allld  # a software portfolio has no storefront; do not invent one
    assert not re.search(r"telephone|email|streetAddress|@gmail", allld)


def test_every_image_has_alt_text_and_no_placeholders(site):
    for p in PAGES:
        for img in Doc(page_file(site, p).read_text()).imgs:
            assert "alt" in img
    for js in (WEB / "js").rglob("*.js"):
        text = js.read_text()
        for m in re.finditer(r"el\('img'", text):
            assert "alt:" in text[m.start(): m.start() + 220], (js, text[m.start(): m.start() + 80])
    for f in list(WEB.rglob("*.js")) + list(WEB.rglob("*.html")) + list(WEB.rglob("*.json")):
        assert not re.search(r"lorem ipsum|TODO|FIXME|React App|Create Vite|Hello world", f.read_text(), re.I), f


def test_internal_links_resolve_and_nothing_is_left_unrendered(site):
    for p in PAGES + [{"path": "/404.html"}]:
        f = page_file(site, p) if p["path"] != "/404.html" else site / "404.html"
        text = f.read_text()
        assert "{{" not in text
        for href in Doc(text).links:
            if href.startswith("/") and not href.startswith("//"):
                target = site / urlparse(href).path.lstrip("/")
                if target.is_dir() or href.endswith("/") or not target.suffix:
                    target = target / "index.html" if target.is_dir() else target
                assert target.exists(), (f, href)


def test_404_page_crawler_files_and_headers(site):
    nf = Doc((site / "404.html").read_text())
    assert nf.meta["robots"] == "noindex, nofollow" and nf.canonical is None and len(nf.h1) == 1
    robots = (site / "robots.txt").read_text()
    assert f"Sitemap: {URL}/sitemap.xml" in robots and "Disallow: /\n" not in robots
    llms = (site / "llms.txt").read_text()
    assert llms.startswith("# RetailPulse") and all(URL + p["path"] in llms for p in PAGES)
    hdr = (site / "_headers").read_text()
    assert "Content-Security-Policy" in hdr and "nosniff" in hdr and "frame-ancestors 'none'" in hdr
    assert Image.open(site / "favicon.ico").format == "ICO"
    assert (site / ".nojekyll").exists() and not (site / "CNAME").exists()


def test_no_source_maps_and_small_javascript(site):
    assert not list(site.rglob("*.map"))
    for f in list(site.rglob("*.js")) + list(site.rglob("*.css")):
        assert "sourceMappingURL" not in f.read_text(errors="ignore")
    js = list((site / "js").rglob("*.js"))
    assert sum(f.stat().st_size for f in js) < 120_000 and max(f.stat().st_size for f in js) < 40_000
    main = (site / "js/main.js").read_text()
    assert "import(path)" in main  # page code is loaded on demand, one module per page


def test_meta_csp_has_no_frame_ancestors_and_exports_are_clean(site):
    x = Doc((site / "index.html").read_text())
    csp = x.meta["Content-Security-Policy"]
    assert "frame-ancestors" not in csp and "script-src 'self'" in csp
    assert not list(site.rglob("*.db")) and not list(site.rglob(".env*"))


def test_base_path_and_cname(tmp_path, built):
    out = tmp_path / "gh"
    info = export_static.export(out, paths=built[0], site_url=f"{URL}/RetailPulse", cname="Retail.Example.IN")
    assert info["base_path"] == "/RetailPulse"
    text = (out / "demand-forecast/index.html").read_text()
    assert 'href="/RetailPulse/css/app.css"' in text and 'src="/RetailPulse/js/main.js"' in text
    assert f'href="{URL}/RetailPulse/demand-forecast/"' in text
    assert (out / "CNAME").read_text() == "retail.example.in\n"
    with pytest.raises(ValueError):
        export_static.export(tmp_path / "bad", paths=built[0], cname="not a domain")
    with pytest.raises(ValueError):
        Site(WEB, site_url="javascript:alert(1)")


def test_page_registry_matches_router_and_templates():
    main = (WEB / "js/main.js").read_text()
    routes = set(re.findall(r"^\s+(\w+): \['[^']+', '\./views/", main, re.M))
    assert routes == {p["key"] for p in PAGES}
    keys = {p["key"] for p in PAGES}
    for p in PAGES:
        assert set(p["related"]) <= keys and (WEB / p["social"]).exists()
    assert len({p["path"] for p in PAGES}) == len(PAGES)
    assert all(p["path"] == "/" or re.fullmatch(r"/[a-z0-9-]+/", p["path"]) for p in PAGES)


# ------------------------------------------------------------------ live server
@pytest.fixture(scope="module")
def live(built):
    return create_app(built[0], keys=ApiKeyStore({}), env="dev", rate_limiter=RateLimiter(6000, 6000))


def test_live_server_renders_pages_but_never_asks_to_be_indexed(live):
    r = request(live, "GET", "/demand-forecast/", {"accept": "text/html"})
    x = Doc(r.body.decode())
    assert r.status == 200 and x.meta["robots"] == "noindex, nofollow" and x.canonical is None
    assert x.meta["rp-mode"] == "live" and len(x.h1) == 1
    assert request(live, "GET", "/demand-forecast", {"accept": "text/html"}).status == 200
    assert request(live, "GET", "/index.html").status == 200


def test_live_server_serves_a_real_404_page_to_browsers_and_json_to_clients(live):
    r = request(live, "GET", "/no-such-page/", {"accept": "text/html,application/xhtml+xml"})
    assert r.status == 404 and "text/html" in r.headers["content-type"]
    assert Doc(r.body.decode()).h1 == ["Page not found"]
    j = request(live, "GET", "/no-such.json", {"accept": "application/json"})
    assert j.status == 404 and j.json() == {"error": "Not found."}
    assert request(live, "GET", "/v1/kpis").status == 200


def test_wrangler_config_is_workers_static_assets():
    import json, re, pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    assert not (root / "wrangler.toml").exists()
    raw = (root / "wrangler.jsonc").read_text()
    cfg = json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))
    assert cfg["name"] == "retailpulse"
    assert cfg["assets"]["directory"] == "./site"
    assert cfg["assets"]["not_found_handling"] == "404-page"
    assert "main" not in cfg
