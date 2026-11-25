import csv
import json
from decimal import Decimal

import pytest
import requests
from openpyxl import load_workbook

from book_scraper.cli import main
from book_scraper.crawl import crawl
from book_scraper.export import summary, to_csv, to_excel, to_json
from book_scraper.fetch import Blocked, Fetcher
from book_scraper.parse import detail, listing, price
from tests.fake_site import BASE, FakeSession, Response, detail_page, listing_page

POETRY = BASE + "catalogue/category/books/poetry_23/index.html"


class Clock:
    """A fake time source: sleeping moves the clock instead of waiting."""

    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(round(seconds, 3))
        self.now += seconds


def fetcher(session=None, delay=0.5, cache=None):
    clock = Clock()
    return Fetcher(delay=delay, session=session or FakeSession(), sleep=clock.sleep, clock=clock, cache=cache), clock


def test_listing_page():
    page = listing(listing_page("catalogue/category/books/poetry_23/index.html").encode(), POETRY, "Poetry")
    assert [book.title for book in page.books] == ["Quiet Hills", "Salt & River", "The Long Walk"]
    first = page.books[0]
    assert first.url == BASE + "catalogue/quiet-hills_1/index.html"      # relative links made absolute
    assert (first.price, first.rating, first.in_stock, first.category) == (Decimal("12.50"), 3, True, "Poetry")
    assert page.books[1].in_stock is False
    assert page.next_url == BASE + "catalogue/category/books/poetry_23/page-2.html"
    assert page.total == 5


def test_detail_page():
    url = BASE + "catalogue/paper-moons_4/index.html"
    book = detail(detail_page("paper-moons_4").encode(), url)
    assert (book.title, book.price, book.rating, book.category) == ("Paper Moons", Decimal("1034.00"), 4, "Poetry")
    assert (book.upc, book.stock, book.reviews, book.in_stock) == ("upc-paper-moons_4", 1, 4, True)
    assert book.image_url == BASE + "media/cache/paper-moons_4.jpg"


def test_price():
    assert price("£51.77") == Decimal("51.77")
    assert price(" £1,034.00 ") == Decimal("1034.00")
    with pytest.raises(ValueError):
        price("free")


def test_crawl_everything_follows_pagination():
    client, _ = fetcher()
    books, failed = crawl(client, log=lambda message: None)
    assert failed == []
    assert len(books) == 6
    assert sorted({book.category for book in books}) == ["Poetry", "Travel"]
    assert client.requests == 5        # robots.txt, home, travel, poetry page 1 and 2


def test_one_category_case_insensitive_and_page_limit():
    client, _ = fetcher()
    books, _ = crawl(client, "poetry", max_pages=1, log=lambda message: None)
    assert [book.title for book in books] == ["Quiet Hills", "Salt & River", "The Long Walk"]
    with pytest.raises(ValueError, match="Known: Poetry, Travel"):
        crawl(fetcher()[0], "cooking", log=lambda message: None)


def test_details_and_a_failing_book_page():
    broken = BASE + "catalogue/north-light_5/index.html"
    session = FakeSession(script={broken: [Response(404)]})
    client, _ = fetcher(session)
    books, failed = crawl(client, "Poetry", details=True, log=lambda message: None)
    by_title = {book.title: book for book in books}
    assert by_title["Quiet Hills"].upc == "upc-quiet-hills_1" and by_title["Quiet Hills"].stock == 4
    assert by_title["North Light"].upc == "" and by_title["North Light"].price == Decimal("23.10")   # listing data kept
    assert failed == [f"{broken}: HTTP 404"]


def test_robots_txt_is_respected():
    session = FakeSession(robots="User-agent: *\nDisallow: /catalogue/\n")
    client, _ = fetcher(session)
    with pytest.raises(Blocked):
        client.get(POETRY)
    assert POETRY not in session.calls


def test_retries_with_backoff_and_retry_after():
    session = FakeSession(script={POETRY: [Response(503), Response(429, headers={"Retry-After": "7"}),
                                           requests.ConnectionError("reset")]})
    client, clock = fetcher(session, delay=0)
    assert b"Quiet Hills" in client.get(POETRY)
    assert clock.slept == [1, 7, 4]                 # 2**0, Retry-After, 2**2
    assert session.calls.count(POETRY) == 4


def test_gives_up_after_the_retries():
    session = FakeSession(script={POETRY: [Response(500)] * 4})
    client, _ = fetcher(session, delay=0)
    with pytest.raises(Exception, match="HTTP 500"):
        client.get(POETRY)


def test_waits_between_requests():
    client, clock = fetcher(delay=0.5)
    client.get(BASE + "index.html")
    clock.now += 0.2                                # the caller spent 0.2 s parsing
    client.get(POETRY)
    assert clock.slept == [0.5, 0.3]                # after robots.txt; then only the remaining 0.3 s


def test_cache_avoids_the_network(tmp_path):
    first, _ = fetcher(cache=tmp_path)
    first.get(POETRY)
    session = FakeSession()
    second, _ = fetcher(session, cache=tmp_path)
    assert b"Quiet Hills" in second.get(POETRY)
    assert session.calls == []


def test_exports(tmp_path):
    books, _ = crawl(fetcher()[0], log=lambda message: None)
    rows = list(csv.DictReader(to_csv(books, tmp_path / "b.csv").open(encoding="utf-8-sig")))
    assert rows[0].keys() >= {"title", "price", "rating", "category", "url"}
    assert {row["title"] for row in rows} >= {"Salt & River", "Maps of Nowhere: A Journey"}
    data = json.loads(to_json(books, tmp_path / "b.json").read_text(encoding="utf-8"))
    assert {"title": "Paper Moons", "price": "1034.00"}.items() <= next(b for b in data if b["title"] == "Paper Moons").items()

    poetry = next(row for row in summary(books) if row[0] == "Poetry")
    assert poetry[:5] == ["Poetry", 5, Decimal("226.27"), Decimal("9.99"), Decimal("1034.00")]
    assert poetry[5:] == [3.0, 4]

    book = load_workbook(to_excel(books, tmp_path / "b.xlsx"))
    assert book.sheetnames == ["Books", "By category"]
    sheet = book["Books"]
    assert sheet["A1"].value == "Title" and sheet.max_row == 7
    assert sheet["I2"].hyperlink.target.startswith(BASE)
    assert book["By category"]["A2"].value == "Poetry"


def test_command_line(tmp_path, capsys):
    client, _ = fetcher()
    code = main(["--category", "Travel", "--details", "-o", str(tmp_path / "t.xlsx"), "--csv", str(tmp_path / "t.csv")],
                fetcher=client)
    assert code == 0
    printed = capsys.readouterr().out
    assert "1 book, 4 requests" in printed
    assert (tmp_path / "t.xlsx").exists() and (tmp_path / "t.csv").exists()
