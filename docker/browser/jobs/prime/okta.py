"""Okta username/password + email-MFA login.

The MFA code is no longer read from a console/file/mailbox here: the platform
supplies it through the runtime input channel. login() takes an `mfa_provider`
callback — `mfa_provider(attempt, max_attempts) -> code` — which the caller
wires to the SDK's request_input().

login()/reauthenticate() also take an optional `snap` callback: a no-arg,
best-effort live-view screenshotter (throttled by the caller) invoked in the
wait loops so the operator can watch the sign-in/MFA screens, not just the
scraping phase.
"""
import logging
import time

from jobs.prime import selectors as SEL
from jobs.prime import ui
from jobs.prime.errors import LoginError, dump_failure

log = logging.getLogger("prime")

MAX_MFA_ATTEMPTS = 3


def _noop():
    pass


def login(page, account, settings, mfa_provider, evidence_dir=None, snap=_noop):
    t = settings.timeouts
    ui.step(f"Opening {settings.login_url} and signing in as {account.username} ...")
    for attempt in (1, 2, 3):
        try:
            page.goto(settings.login_url, wait_until="domcontentloaded",
                      timeout=t.default_ms * attempt)
            break
        except Exception as e:
            if attempt == 3:
                raise LoginError(f"Could not load the login page after 3 tries: {e}")
            ui.warn(f"Login page slow to load (try {attempt}/3), retrying ...")
    snap()

    _fill_credentials(page, account, t, snap)

    states = {
        "dashboard": SEL.DASHBOARD_MARKER,
        "tile": SEL.EINVOICE_TILE,
        "send_email": SEL.OKTA_SEND_EMAIL_BTN,
        "email_select": SEL.OKTA_CHOOSER_EMAIL,
        "code_input": SEL.OKTA_CODE_INPUT,
        "error": SEL.OKTA_ERROR,
    }
    state = _wait_any(page, states, t.default_ms, snap)
    if state == "email_select":
        page.locator(SEL.OKTA_CHOOSER_EMAIL).first.click()
        del states["email_select"]
        state = _wait_any(page, states, t.default_ms, snap)

    if state == "error":
        raise LoginError(f"Okta rejected the credentials: {_error_text(page)}")
    if state in ("dashboard", "tile"):
        ui.success("Signed in (no MFA challenge this time).")
        return

    _enter_code_loop(page, t, mfa_provider, evidence_dir, snap)
    ui.success("MFA verified - signed in.")


def reauthenticate(page, account, settings, mfa_provider, evidence_dir=None,
                   snap=_noop):
    """Re-establish the session after the portal bounces us back to Okta
    mid-run. Unlike login(), it tolerates landing on any state: a fresh sign-in
    form, a step-up MFA challenge (no credentials re-asked), or an already-
    restored dashboard. Dispatches a fresh MFA request via mfa_provider."""
    t = settings.timeouts
    ui.warn("Re-authenticating — the portal asked us to sign in again ...")
    for attempt in (1, 2, 3):
        try:
            page.goto(settings.login_url, wait_until="domcontentloaded",
                      timeout=t.default_ms * attempt)
            break
        except Exception as e:
            if attempt == 3:
                raise LoginError(f"Could not reload the login page for re-auth: {e}")
            ui.warn(f"Login page slow to load (try {attempt}/3), retrying ...")
    snap()

    entry = {
        "dashboard": SEL.DASHBOARD_MARKER, "tile": SEL.EINVOICE_TILE,
        "username": SEL.OKTA_USERNAME, "send_email": SEL.OKTA_SEND_EMAIL_BTN,
        "email_select": SEL.OKTA_CHOOSER_EMAIL, "code_input": SEL.OKTA_CODE_INPUT,
        "error": SEL.OKTA_ERROR,
    }
    state = _wait_any(page, entry, t.default_ms, snap)
    if state in ("dashboard", "tile"):
        ui.success("Session already restored.")
        return
    if state == "error":
        raise LoginError(f"Okta rejected re-auth: {_error_text(page)}")
    if state == "username":
        _fill_credentials(page, account, t, snap)
        state = _wait_any(page, {k: v for k, v in entry.items() if k != "username"},
                          t.default_ms, snap)
    if state == "email_select":
        page.locator(SEL.OKTA_CHOOSER_EMAIL).first.click()
        state = _wait_any(page, {k: v for k, v in entry.items()
                                 if k not in ("username", "email_select")},
                          t.default_ms, snap)
    if state == "error":
        raise LoginError(f"Okta rejected re-auth: {_error_text(page)}")
    if state in ("dashboard", "tile"):
        ui.success("Re-authenticated (no MFA challenge).")
        return
    _enter_code_loop(page, t, mfa_provider, evidence_dir, snap)
    ui.success("Re-authenticated via MFA.")


def _fill_credentials(page, account, t, snap=_noop):
    user = page.locator(SEL.OKTA_USERNAME).first
    user.wait_for(state="visible", timeout=t.default_ms)
    user.fill(account.username)

    pwd = page.locator(SEL.OKTA_PASSWORD).first
    if not _is_visible(pwd):
        page.locator(SEL.OKTA_SUBMIT).first.click()  # identifier-first: Next
        state = _wait_any(page, {
            "password": SEL.OKTA_PASSWORD,
            "chooser": SEL.OKTA_CHOOSER_PASSWORD,
            "error": SEL.OKTA_ERROR,
        }, t.default_ms, snap)
        if state == "error":
            raise LoginError(f"Okta rejected the username: {_error_text(page)}")
        if state == "chooser":
            page.locator(SEL.OKTA_CHOOSER_PASSWORD).first.click()
            pwd.wait_for(state="visible", timeout=t.default_ms)
    pwd.fill(account.password)
    page.locator(SEL.OKTA_SUBMIT).first.click()
    snap()


def _ensure_code_entry_ui(page, t, snap=_noop):
    deadline = time.monotonic() + 2 * t.default_ms / 1000
    sends_clicked = 0
    while time.monotonic() < deadline:
        snap()
        send_btn = page.locator(SEL.OKTA_SEND_EMAIL_BTN).first
        if sends_clicked < 2 and _is_visible(send_btn):
            ui.step("Requesting the verification email ...")
            try:
                send_btn.click(timeout=3000)
                sends_clicked += 1
            except Exception as e:
                log.debug("send-email click failed: %s", e)
            time.sleep(1)
            continue
        clicked_link = False
        for candidate in SEL.OKTA_ENTER_CODE_CANDIDATES:
            link = page.locator(candidate).first
            if _is_visible(link):
                try:
                    link.click(timeout=3000)
                    clicked_link = True
                except Exception as e:
                    log.debug("link click failed: %s", e)
                break
        if clicked_link:
            time.sleep(0.5)
        if _is_visible(page.locator(SEL.OKTA_CODE_INPUT).first):
            return
        time.sleep(0.5)
    raise LoginError("The verification-code entry field never became visible.")


def _enter_code_loop(page, t, mfa_provider, evidence_dir=None, snap=_noop):
    deadline = time.monotonic() + t.mfa_total_ms / 1000
    for attempt in range(1, MAX_MFA_ATTEMPTS + 1):
        if time.monotonic() > deadline:
            raise LoginError("MFA timed out waiting for the code.")
        _ensure_code_entry_ui(page, t, snap)
        if evidence_dir:
            dump_failure(page, evidence_dir, f"mfa_screen_attempt{attempt}")
        snap()  # capture the code-entry screen before the (possibly long) wait
        # The platform resolves this (mailbox provider or operator).
        code = mfa_provider(attempt, MAX_MFA_ATTEMPTS)
        if _signed_in(page):
            return
        try:
            box = page.locator(SEL.OKTA_CODE_INPUT).first
            box.fill(code, timeout=10000)
            page.locator(SEL.OKTA_VERIFY_BTN).first.click()
        except Exception as e:
            if _signed_in(page):
                return
            raise LoginError(f"Could not enter the verification code: {e}")
        state = _wait_any(page, {
            "dashboard": SEL.DASHBOARD_MARKER,
            "tile": SEL.EINVOICE_TILE,
            "error": SEL.OKTA_ERROR,
        }, t.default_ms, snap)
        if state in ("dashboard", "tile"):
            return
        ui.warn(f"Okta did not accept that code: {_error_text(page)}")
    raise LoginError(f"MFA failed after {MAX_MFA_ATTEMPTS} attempts.")


def _signed_in(page):
    return (_is_visible(page.locator(SEL.DASHBOARD_MARKER).first)
            or _is_visible(page.locator(SEL.EINVOICE_TILE).first))


def _error_text(page):
    try:
        return page.locator(SEL.OKTA_ERROR).first.inner_text(timeout=2000).strip() or "(no message)"
    except Exception:
        return "(no message)"


def _is_visible(locator):
    try:
        return locator.is_visible(timeout=1500)
    except Exception:
        return False


def _wait_any(page, named_selectors, timeout_ms, snap=_noop):
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        snap()
        for name, sel in named_selectors.items():
            try:
                if page.locator(sel).first.is_visible(timeout=200):
                    return name
            except Exception:
                continue
        time.sleep(0.3)
    raise LoginError(f"Timed out waiting for one of: {list(named_selectors)} "
                     f"(current url: {page.url})")
