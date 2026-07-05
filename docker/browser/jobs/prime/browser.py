"""Playwright lifecycle: headed browser with downloads enabled."""
import logging
import os
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

log = logging.getLogger("prime")


def _screen_size() -> tuple[int, int]:
    """Parse the Xvfb screen (DATAPULL_SCREEN='WxHxD') so the browser window can
    fill it exactly — there's no window manager under Xvfb, so --start-maximized
    doesn't work and the unfilled display would show as a black border."""
    try:
        w, h = os.environ.get("DATAPULL_SCREEN", "1280x1024x24").split("x")[:2]
        return int(w), int(h)
    except Exception:
        return 1280, 1024


@contextmanager
def launch(settings):
    """Yields (context, page). Headed by default (runs under Xvfb in the
    container); Okta challenges headless browsers more aggressively."""
    width, height = _screen_size()
    with sync_playwright() as pw:
        launch_kwargs = {
            "headless": not settings.headed,
            # --no-sandbox: required for Chromium in an unprivileged container.
            # Size the window to the whole display (no WM to maximize it).
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--window-position=0,0",
                f"--window-size={width},{height}",
            ],
        }
        if settings.browser_channel:
            launch_kwargs["channel"] = settings.browser_channel
            log.info("launching via channel=%s", settings.browser_channel)
        browser = pw.chromium.launch(**launch_kwargs)
        # ignore_https_errors: the corporate network does TLS interception (and
        # internal endpoints use non-public certs), so the Okta sign-in widget's
        # CDN assets (oktacdn.com) otherwise fail with ERR_CERT_AUTHORITY_INVALID.
        # When that happens the widget JS never initializes and the page shows
        # its static "Cookies are disabled" fallback — a misleading symptom of a
        # cert problem, not a real cookie problem. (rcm_login sets this too.)
        context = browser.new_context(
            accept_downloads=True, no_viewport=True, ignore_https_errors=True
        )
        context.set_default_timeout(settings.timeouts.default_ms)
        page = context.new_page()
        try:
            yield context, page
        finally:
            try:
                browser.close()
            except Exception:
                pass
