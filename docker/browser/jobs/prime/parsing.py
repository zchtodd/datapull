"""Data shapes + scraping helpers for the eInvoice results table."""
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("prime")


@dataclass
class Combo:
    business_line: str
    program: str
    year_qtr: str


@dataclass
class ResultRow:
    invoice_no: str
    manufacturer: str
    labeler: str
    status: str = ""
    page_index: int = 1


@dataclass
class Option:
    value: str
    label: str


INVOICE_NO_RE = re.compile(r"^[A-Z0-9]+-\S+")


def scrape_rows(page, row_selector, page_index):
    """Reads the visible results rows. Cell layout:
    [checkbox] [Invoice Number] [Manufacturer Name] [Labeler Code] [Status]."""
    rows = []
    for tr in page.locator(row_selector).all():
        cells = [c.strip() for c in tr.locator("td").all_inner_texts()]
        texts = [c for c in cells if c]
        if len(texts) < 2:
            continue
        invoice_no = texts[0]
        if not INVOICE_NO_RE.match(invoice_no):
            log.debug("skipping non-data row: %r", cells)
            continue
        rows.append(ResultRow(
            invoice_no=invoice_no,
            manufacturer=texts[1] if len(texts) > 1 else "",
            labeler=texts[2] if len(texts) > 2 else "",
            status=texts[3] if len(texts) > 3 else "",
            page_index=page_index,
        ))
    return rows


def quarter_from_invoice_no(invoice_no):
    """'AZADAP-1Q26-59148' -> '20261', or None. Cross-check only."""
    m = re.search(r"\b([1-4])Q(\d{2})\b", invoice_no)
    if m:
        return f"20{m.group(2)}{m.group(1)}"
    return None
