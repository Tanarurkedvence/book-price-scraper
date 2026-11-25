"""CSV and JSON for other programs, Excel (with a per-category summary) for people."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict, fields
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

from .parse import Book

COLUMNS = [field.name for field in fields(Book)]


def _rows(books: list[Book]) -> list[dict]:
    return [{key: (str(value) if isinstance(value, Decimal) else value) for key, value in asdict(book).items()}
            for book in books]


def to_csv(books: list[Book], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:          # -sig: Excel opens it correctly
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(_rows(books))
    return path


def to_json(books: list[Book], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_rows(books), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def summary(books: list[Book]) -> list[list]:
    """Per category: books, average price, cheapest, most expensive, average rating, in stock."""
    groups: dict[str, list[Book]] = defaultdict(list)
    for book in books:
        groups[book.category or "(none)"].append(book)
    rows = []
    for name, items in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        prices = [book.price for book in items]
        rows.append([name, len(items), (sum(prices) / len(prices)).quantize(Decimal("0.01")), min(prices),
                     max(prices), round(sum(book.rating for book in items) / len(items), 2),
                     sum(book.in_stock for book in items)])
    return rows


def _table(sheet, name: str, headers: list[str], rows: list[list], widths: list[int], formats: dict[int, str]):
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    for column, fmt in formats.items():
        for (cell,) in sheet.iter_rows(min_row=2, min_col=column, max_col=column):
            cell.number_format = fmt
    last = chr(64 + len(headers))
    table = Table(displayName=name, ref=f"A1:{last}{max(len(rows), 1) + 1}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    sheet.add_table(table)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.freeze_panes = "A2"


def to_excel(books: list[Book], path: str | Path, currency: str = "£") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    money = f'"{currency}"#,##0.00'
    book = Workbook()
    sheet = book.active
    sheet.title = "Books"
    _table(sheet, "Books", ["Title", "Category", "Price", "Rating", "In stock", "Available", "Reviews", "UPC", "URL"],
           [[b.title, b.category, b.price, b.rating, "yes" if b.in_stock else "no", b.stock, b.reviews, b.upc, b.url]
            for b in books], [48, 20, 10, 8, 9, 10, 9, 18, 70], {3: money})
    for row in range(2, len(books) + 2):
        cell = sheet.cell(row=row, column=9)
        cell.hyperlink = cell.value
    _table(book.create_sheet("By category"), "ByCategory",
           ["Category", "Books", "Average price", "Cheapest", "Most expensive", "Average rating", "In stock"],
           summary(books), [24, 8, 14, 11, 15, 15, 10], {3: money, 4: money, 5: money, 6: "0.00"})
    book.save(path)
    return path
