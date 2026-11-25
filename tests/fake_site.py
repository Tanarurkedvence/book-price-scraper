"""A tiny fictional shop with the same markup as books.toscrape.com, served without a network.

Category "Poetry" has two listing pages (3 + 2 books), "Travel" has one (1 book).
"""

from __future__ import annotations

from dataclasses import dataclass, field

BASE = "https://books.toscrape.com/"
WORDS = ["Zero", "One", "Two", "Three", "Four", "Five"]


@dataclass
class Response:
    status_code: int
    content: bytes = b""
    headers: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")


BOOKS = {   # slug: (title, price, rating, stock, category)
    "quiet-hills_1": ("Quiet Hills", "12.50", 3, 4, "Poetry"),
    "salt-and-river_2": ("Salt & River", "51.77", 5, 0, "Poetry"),
    "the-long-walk_3": ("The Long Walk", "9.99", 1, 12, "Poetry"),
    "paper-moons_4": ("Paper Moons", "1,034.00", 4, 1, "Poetry"),
    "north-light_5": ("North Light", "23.10", 2, 7, "Poetry"),
    "maps-of-nowhere_6": ("Maps of Nowhere: A Journey", "45.17", 2, 19, "Travel"),
}
PAGES = {
    "catalogue/category/books/poetry_23/index.html": ["quiet-hills_1", "salt-and-river_2", "the-long-walk_3"],
    "catalogue/category/books/poetry_23/page-2.html": ["paper-moons_4", "north-light_5"],
    "catalogue/category/books/travel_2/index.html": ["maps-of-nowhere_6"],
}


def pod(slug: str) -> str:
    title, price, stars, stock, _ = BOOKS[slug]
    availability = "In stock" if stock else "Out of stock"
    return f"""
<article class="product_pod">
  <div class="image_container"><a href="../../../{slug}/index.html">
    <img src="../../../../media/cache/{slug}.jpg" alt="{title}" class="thumbnail"></a></div>
  <p class="star-rating {WORDS[stars]}"><i class="icon-star"></i></p>
  <h3><a href="../../../{slug}/index.html" title="{title}">{title[:12]}...</a></h3>
  <div class="product_price"><p class="price_color">£{price}</p>
    <p class="instock availability"><i class="icon-ok"></i> {availability}</p></div>
</article>"""


def listing_page(path: str) -> str:
    slugs = PAGES[path]
    folder = path.rsplit("/", 1)[0]
    total = sum(len(s) for p, s in PAGES.items() if p.startswith(folder))
    pager = ""
    if path.endswith("poetry_23/index.html"):
        pager = '<ul class="pager"><li class="current">Page 1 of 2</li><li class="next"><a href="page-2.html">next</a></li></ul>'
    elif path.endswith("page-2.html"):
        pager = '<ul class="pager"><li class="previous"><a href="index.html">previous</a></li><li class="current">Page 2 of 2</li></ul>'
    return f"""<html><head><meta charset="utf-8"></head><body>
<form class="form-horizontal"><strong>{total}</strong> results.</form>
<ol class="row">{''.join(pod(slug) for slug in slugs)}</ol>{pager}</body></html>"""


def home_page() -> str:
    return """<html><head><meta charset="utf-8"></head><body><div class="side_categories"><ul><li>
<a href="catalogue/category/books_1/index.html">Books</a><ul>
<li><a href="catalogue/category/books/travel_2/index.html">Travel</a></li>
<li><a href="catalogue/category/books/poetry_23/index.html">Poetry</a></li>
</ul></li></ul></div></body></html>"""


def detail_page(slug: str) -> str:
    title, price, stars, stock, category = BOOKS[slug]
    availability = f"In stock ({stock} available)" if stock else "Out of stock (0 available)"
    return f"""<html><head><meta charset="utf-8"></head><body>
<ul class="breadcrumb"><li><a href="../../index.html">Home</a></li><li><a href="#">Books</a></li>
<li><a href="#">{category}</a></li><li class="active">{title}</li></ul>
<div id="product_gallery"><div class="item active"><img src="../../media/cache/{slug}.jpg" alt="{title}"></div></div>
<div class="product_main"><h1>{title}</h1><p class="price_color">£{price}</p>
<p class="instock availability">{availability}</p><p class="star-rating {WORDS[stars]}"></p></div>
<table class="table table-striped"><tr><th>UPC</th><td>upc-{slug}</td></tr>
<tr><th>Availability</th><td>{availability}</td></tr><tr><th>Number of reviews</th><td>{stars}</td></tr></table>
</body></html>"""


class FakeSession:
    """Behaves like requests.Session.get. `script` lets a test return errors for a URL first."""

    def __init__(self, robots: str | None = None, script: dict | None = None):
        self.headers: dict = {}
        self.robots = robots
        self.script = {url: list(steps) for url, steps in (script or {}).items()}
        self.calls: list[str] = []

    def get(self, url: str, timeout: float = 0) -> Response:
        self.calls.append(url)
        if self.script.get(url):
            step = self.script[url].pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        path = url.removeprefix(BASE)
        if path == "robots.txt":
            return Response(200, self.robots.encode()) if self.robots is not None else Response(404, b"not found")
        if path == "index.html":
            return Response(200, home_page().encode())
        if path in PAGES:
            return Response(200, listing_page(path).encode())
        slug = path.removeprefix("catalogue/").removesuffix("/index.html")
        if slug in BOOKS:
            return Response(200, detail_page(slug).encode())
        return Response(404, b"not found")
