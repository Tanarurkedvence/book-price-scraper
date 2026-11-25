"""python -m book_scraper [--category Travel] [--pages 2] [--details] [-o books.xlsx] [--csv …] [--json …]"""

from __future__ import annotations

import argparse
import sys
import time

from .crawl import crawl
from .export import to_csv, to_excel, to_json
from .fetch import Blocked, Fetcher


def main(argv: list[str] | None = None, fetcher: Fetcher | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="book_scraper", description="Scrape books.toscrape.com politely.")
    parser.add_argument("--category", help="only this category, e.g. Travel (default: all)")
    parser.add_argument("--pages", type=int, help="at most this many listing pages per category")
    parser.add_argument("--details", action="store_true", help="also open every book page (UPC, stock, reviews)")
    parser.add_argument("-o", "--output", default="output/books.xlsx", help="Excel file")
    parser.add_argument("--csv", help="also write CSV")
    parser.add_argument("--json", help="also write JSON")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between requests (default 0.5)")
    parser.add_argument("--cache", help="keep downloaded pages in this folder")
    args = parser.parse_args(argv)

    fetcher = fetcher or Fetcher(delay=args.delay, cache=args.cache, log=print)
    started = time.monotonic()
    try:
        books, failed = crawl(fetcher, args.category, args.pages, args.details)
    except (ValueError, Blocked) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    if not books:
        print("No books found.", file=sys.stderr)
        return 1

    plural = "" if len(books) == 1 else "s"
    print(f"\n{len(books)} book{plural}, {fetcher.requests} requests, {time.monotonic() - started:.0f} s")
    print(f"Excel: {to_excel(books, args.output)}")
    if args.csv:
        print(f"CSV:   {to_csv(books, args.csv)}")
    if args.json:
        print(f"JSON:  {to_json(books, args.json)}")
    if failed:
        print(f"{len(failed)} page(s) failed:", *failed[:5], sep="\n  ")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
