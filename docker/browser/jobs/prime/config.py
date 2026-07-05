"""Configuration for the ported Prime scraper, built from PARAM_* env vars.

The platform passes each job parameter as PARAM_<KEY>. Secrets (e.g. the
account password) are decrypted upstream before becoming env values. The MFA
mailbox is NOT configured here — it's a platform connection the runtime input
channel uses; this job only requests the code.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

REPORT_PDF = "View Combined Invoice in PDF Format"
REPORT_CMS = "Export in CMS Format"


def _param(key, default=None):
    return os.environ.get(f"PARAM_{key}", default)


def _bool(key, default=False):
    v = _param(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _int(key, default=0):
    v = _param(key)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@dataclass
class Timeouts:
    default_ms: int = 30000
    postback_ms: int = 45000
    download_ms: int = 120000
    # How long to wait for an MFA code to be supplied (mailbox auto-provider or
    # an operator in the UI). Long by design: an operator may not notice the
    # prompt for hours, and the run must survive that wait rather than fail.
    mfa_total_ms: int = 43200000  # 12 hours


@dataclass
class Settings:
    login_url: str
    browser_channel: str = ""
    headed: bool = True
    timeouts: Timeouts = field(default_factory=Timeouts)
    skip_option_labels: list = field(default_factory=list)
    # Pause before each server-hitting action (dropdown change, Continue,
    # Search, download click) to avoid hammering the portal. 0 disables it.
    throttle_ms: int = 2000
    # How many times to re-attempt the invoices that failed on a results page
    # (with a fresh search) before recording them as failures. Absorbs transient
    # portal hiccups in-session instead of escalating to a whole-run resume.
    download_retries: int = 2
    # Minimum gap (ms) between consecutive Search submissions. Sweeping an empty
    # quarter fires many back-to-back searches (each combo returns no records
    # and settles instantly), which trips a portal 403; this floors the
    # submission rate. Searches separated by real download work aren't delayed.
    search_interval_ms: int = 8000


@dataclass
class Account:
    username: str
    password: str


@dataclass
class Args:
    """Run-scoping flags (subset of the original CLI)."""
    only_business_line: str = ""
    only_program: str = ""
    max_rows: int = 0
    dry_run: bool = False
    keep_open: bool = False
    recon: bool = False
    watch: bool = False


def load_settings() -> Settings:
    skip_raw = _param("SKIP_OPTION_LABELS", "")
    try:
        skip = json.loads(skip_raw) if skip_raw.strip().startswith("[") else \
            [s for s in skip_raw.split(",")]
    except Exception:
        skip = []
    skip = [s.strip().lower() for s in skip if s and s.strip()]
    if not skip:
        skip = ["", "select", "select one", "--select--", "all"]
    return Settings(
        login_url=_param("LOGIN_URL", ""),
        browser_channel=_param("BROWSER_CHANNEL", "") or "",
        headed=_bool("HEADED", True),
        timeouts=Timeouts(
            default_ms=_int("TIMEOUT_DEFAULT_MS", 30000),
            postback_ms=_int("TIMEOUT_POSTBACK_MS", 45000),
            download_ms=_int("TIMEOUT_DOWNLOAD_MS", 120000),
            mfa_total_ms=_int("TIMEOUT_MFA_TOTAL_MS", 43200000),
        ),
        skip_option_labels=skip,
        throttle_ms=_int("THROTTLE_MS", 2000),
        download_retries=_int("DOWNLOAD_RETRIES", 2),
        search_interval_ms=_int("SEARCH_INTERVAL_MS", 8000),
    )


def load_account() -> Account:
    username = _param("ACCOUNT_USERNAME", "")
    password = _param("ACCOUNT_PASSWORD", "")
    if not username or not password:
        raise ValueError("ACCOUNT_USERNAME and ACCOUNT_PASSWORD parameters are required")
    return Account(username=username, password=password)


def load_programs() -> dict:
    raw = _param("PROGRAMS", "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"PROGRAMS is not valid JSON: {e}") from e
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def load_args() -> Args:
    return Args(
        only_business_line=_param("ONLY_BUSINESS_LINE", "") or "",
        only_program=_param("ONLY_PROGRAM", "") or "",
        max_rows=_int("MAX_ROWS", 0),
        dry_run=_bool("DRY_RUN", False),
    )


def quarter_override() -> str | None:
    q = (_param("QUARTER", "") or "").strip()
    if len(q) == 5 and q.isdigit() and q[4] in "1234":
        return q
    return None


def output_dir() -> Path:
    return Path(os.environ.get("DATAPULL_OUTPUT_DIR", "/data/outputs/run"))
