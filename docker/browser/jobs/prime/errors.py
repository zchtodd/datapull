"""Error taxonomy + failure evidence capture."""
import logging
from datetime import datetime

log = logging.getLogger("prime")


class PortalError(Exception):
    """Recoverable portal-level problem (row/combo can be skipped)."""


class LoginError(Exception):
    """Fatal: could not authenticate."""


class SessionExpiredError(Exception):
    """Fatal: portal session died mid-run. Re-running resumes safely."""


class PortalForbiddenError(Exception):
    """Fatal: the portal returned 403 Forbidden (blocked / access denied)."""


class ReauthRequired(Exception):
    """Recoverable: the portal bounced us back to an Okta sign-in / MFA screen
    mid-run. The caller re-authenticates (dispatching a fresh MFA request) and
    retries the work in progress."""


def dump_failure(page, run_dir, tag):
    """Best-effort screenshot + HTML dump. Never raises."""
    stamp = datetime.now().strftime("%H%M%S")
    safe_tag = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)[:80]
    base = run_dir / f"fail_{stamp}_{safe_tag}"
    try:
        page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
    except Exception as e:
        log.debug("screenshot failed: %s", e)
    try:
        base.with_suffix(".html").write_text(page.content(), encoding="utf-8")
    except Exception as e:
        log.debug("html dump failed: %s", e)
    log.error("failure evidence saved: %s.*", base)
    return base
