"""Walk the listing pages (and optionally every book page) and collect the books."""

from __future__ import annotations

from .fetch import FetchError, Fetcher
from .parse import Book, categories, detail, listing

HOME = "https://books.toscrape.com/index.html"


def crawl_listing(fetcher: Fetcher, start: str, category: str = "", max_pages: int | None = None,
                  log=print) -> list[Book]:
    books: list[Book] = []
    url, page = start, 0
    while url and (max_pages is None or page < max_pages):
        page += 1
        result = listing(fetcher.get(url), url, category)
        books += result.books
        log(f"  page {page}: {len(result.books)} books" + (f" (of {result.total})" if result.total and page == 1 else ""))
        url = result.next_url
    return books


def crawl(fetcher: Fetcher, category: str | None = None, max_pages: int | None = None, details: bool = False,
          log=print) -> tuple[list[Book], list[str]]:
    """All books (or one category's). Returns the books and the URLs that failed."""
    home = fetcher.get(HOME)
    sections = categories(home, HOME)
    if category:
        match = {name.lower(): name for name in sections}.get(category.lower())
        if not match:
            raise ValueError(f"unknown category {category!r}. Known: {', '.join(sorted(sections))}")
        sections = {match: sections[match]}

    books: list[Book] = []
    failed: list[str] = []
    for name, url in sections.items():
        log(f"{name}")
        try:
            books += crawl_listing(fetcher, url, name, max_pages, log)
        except FetchError as err:
            failed.append(str(err))
            log(f"  failed: {err}")

    if details:
        log(f"Reading {len(books)} book pages …")
        enriched = []
        for index, book in enumerate(books, start=1):
            try:
                enriched.append(detail(fetcher.get(book.url), book.url))
            except FetchError as err:
                failed.append(str(err))
                enriched.append(book)               # keep what the listing gave us
            if index % 50 == 0:
                log(f"  {index}/{len(books)}")
        books = enriched
    return books, failed
