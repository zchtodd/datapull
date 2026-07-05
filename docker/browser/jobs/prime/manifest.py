"""Per-run audit manifest (CSV) + debug log, written into the output dir so
they're captured alongside the downloaded files as run artifacts.
"""
import csv
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

COLUMNS = ["timestamp", "account", "business_line", "program", "year_qtr", "page",
           "invoice_no", "labeler", "manufacturer", "report_type", "status",
           "file_path", "portal_suggested_name", "error"]

log = logging.getLogger("prime")


class RunManifest:
    def __init__(self, run_dir: Path, account_username: str):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.run_dir / "manifest.csv"
        self.account = account_username
        self.counts = Counter()
        self._fh = open(self.csv_path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=COLUMNS)
        self._writer.writeheader()
        self._setup_logging()

    def _setup_logging(self):
        log.setLevel(logging.DEBUG)
        fh = logging.FileHandler(self.run_dir / "run.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(fh)
        log.debug("Run started, account=%s", self.account)

    def record(self, status, combo=None, row=None, report_type="", file_path="",
               suggested_name="", error="", page=""):
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "account": self.account,
            "business_line": combo.business_line if combo else "",
            "program": combo.program if combo else "",
            "year_qtr": combo.year_qtr if combo else "",
            "page": page or (row.page_index if row else ""),
            "invoice_no": row.invoice_no if row else "",
            "labeler": row.labeler if row else "",
            "manufacturer": row.manufacturer if row else "",
            "report_type": report_type,
            "status": status,
            "file_path": str(file_path) if file_path else "",
            "portal_suggested_name": suggested_name,
            "error": error,
        }
        self._writer.writerow(entry)
        self._fh.flush()
        self.counts[status] += 1
        log.debug("manifest: %s", entry)

    def close(self):
        log.debug("Run finished, counts=%s", dict(self.counts))
        self._fh.close()
