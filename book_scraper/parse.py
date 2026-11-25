"""Turn the shop's HTML into data. Only this file knows the page structure,
so if the site changes its markup, this is the one place to update."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup

RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@dataclass
class Book:
    title: str
    url: str
    price: Decimal
    rating: int
    in_stock: bool
    category: str = ""
    upc: str = ""
    stock: int | None = None            # number available; only on the detail page
    reviews: int | None = None
    image_url: str = ""


@dataclass
class Listing:
    books: list[Book]
    next_url: str | None
    total: int | None                   # "1000 results" on the first page


def _soup(html: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")       # bytes: the parser reads the page's own charset


def price(text: str) -> Decimal:
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        raise ValueError(f"no price in {text!r}")
    return Decimal(match.group())


def rating(tag) -> int:
    classes = tag.get("class", []) if tag else []
    return next((RATINGS[name] for name in classes if name in RATINGS), 0)


def listing(html: bytes | str, url: str, category: str = "") -> Listing:
    soup = _soup(html)
    books = []
    for pod in soup.select("article.product_pod"):
        link = pod.select_one("h3 a")
        books.append(Book(
            title=link.get("title") or link.get_text(strip=True),
            url=urljoin(url, link["href"]),
            price=price(pod.select_one("p.price_color").get_text()),
            rating=rating(pod.select_one("p.star-rating")),
            in_stock="in stock" in pod.select_one("p.availability").get_text(" ", strip=True).lower(),
            category=category,
            image_url=urljoin(url, pod.select_one("img")["src"]) if pod.select_one("img") else "",
        ))
    next_link = soup.select_one("ul.pager li.next a")
    count = soup.select_one("form.form-horizontal strong")
    return Listing(books, urljoin(url, next_link["href"]) if next_link else None,
                   int(count.get_text(strip=True)) if count and count.get_text(strip=True).isdigit() else None)


def categories(html: bytes | str, url: str) -> dict[str, str]:
    """Category name → first page URL, from the sidebar."""
    soup = _soup(html)
    return {link.get_text(strip=True): urljoin(url, link["href"])
            for link in soup.select("div.side_categories ul li ul li a")}


def detail(html: bytes | str, url: str) -> Book:
    soup = _soup(html)
    main = soup.select_one("div.product_main")
    table = {row.th.get_text(strip=True): row.td.get_text(strip=True) for row in soup.select("table.table tr")}
    crumbs = [item.get_text(strip=True) for item in soup.select("ul.breadcrumb li")]
    availability = table.get("Availability") or main.select_one("p.availability").get_text(" ", strip=True)
    count = re.search(r"\((\d+) available\)", availability)
    image = soup.select_one("div.item.active img") or soup.select_one("#product_gallery img")
    return Book(
        title=main.h1.get_text(strip=True),
        url=url,
        price=price(main.select_one("p.price_color").get_text()),
        rating=rating(main.select_one("p.star-rating")),
        in_stock="in stock" in availability.lower(),
        category=crumbs[-2] if len(crumbs) >= 3 else "",
        upc=table.get("UPC", ""),
        stock=int(count.group(1)) if count else 0,
        reviews=int(table["Number of reviews"]) if table.get("Number of reviews", "").isdigit() else None,
        image_url=urljoin(url, image["src"]) if image else "",
    )
