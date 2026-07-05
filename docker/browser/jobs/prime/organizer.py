"""Folder/file naming rules and idempotency.

Target layout:
    <output root>/<STATE> <YYYY-QQ>/<labeler>/<STATE> <YYYY-QQ> <SHORT> <INVOICE_NO> Invoice.<ext>

STATE/SHORT come from the PROGRAMS map keyed by the portal's Program Name.
Unmapped programs still download, under an UNMAPPED folder.
"""
import logging
import re
import shutil
from pathlib import Path

from jobs.prime.config import REPORT_PDF

log = logging.getLogger("prime")

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str) -> str:
    return re.sub(r"\s+", " ", _INVALID.sub("", name)).strip()


def quarter_label(yyyyq: str) -> str:
    if not (yyyyq and len(yyyyq) == 5 and yyyyq.isdigit() and yyyyq[4] in "1234"):
        raise ValueError(f"Bad year-quarter value: {yyyyq!r} (expected YYYYQ)")
    return f"{yyyyq[:4]}-{yyyyq[4]}Q"


class Organizer:
    def __init__(self, output_root: Path, programs: dict):
        self.output_root = Path(output_root)
        self.programs = programs
        self._warned_programs = set()

    def program_info(self, program_name: str):
        info = self.programs.get(program_name)
        if info and info.get("state") and info.get("short"):
            return info["state"], info["short"], True
        if program_name not in self._warned_programs:
            self._warned_programs.add(program_name)
            log.warning("Program '%s' is not mapped - files go under UNMAPPED.", program_name)
        return None, None, False

    def target_path(self, combo, row, report_type, suggested_ext=None) -> Path:
        qlabel = quarter_label(combo.year_qtr)
        state, short, mapped = self.program_info(combo.program)
        if report_type == REPORT_PDF:
            ext = ".pdf"
        else:
            ext = suggested_ext if suggested_ext else ".txt"
        if mapped:
            folder = self.output_root / f"{state} {qlabel}" / sanitize(row.labeler)
            stem = f"{state} {qlabel} {short} {row.invoice_no} Invoice"
        else:
            folder = self.output_root / f"UNMAPPED {qlabel}" / sanitize(row.labeler)
            stem = f"{sanitize(combo.program)} {qlabel} {row.invoice_no} Invoice"
        return folder / f"{sanitize(stem)}{ext}"

    def existing_file(self, combo, row, report_type):
        default_target = self.target_path(combo, row, report_type)
        if report_type == REPORT_PDF:
            return default_target if default_target.exists() else None
        if not default_target.parent.exists():
            return None
        for candidate in default_target.parent.glob(default_target.stem + ".*"):
            if candidate.suffix.lower() != ".pdf":
                return candidate
        return None

    def place(self, temp_path: Path, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_path), str(target))
        log.info("saved %s", target)
        return target
