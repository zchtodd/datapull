"""Test login job: open a login page and sign in. Exercises the platform
end to end (DooD launch, account connection, live view) without the full Prime
flow. Selectors are best-effort with overridable defaults.

Params (PARAM_*):
  LOGIN_URL            default https://rcm-ga.rsmus.com:8443/login
  ACCOUNT_USERNAME     from the bound account connection
  ACCOUNT_PASSWORD     from the bound account connection (secret)
  USERNAME_SELECTOR / PASSWORD_SELECTOR / SUBMIT_SELECTOR   optional overrides
  DWELL_SECONDS        keep the browser open after login so live view can watch
"""
import os
import time

from playwright.sync_api import sync_playwright


def _param(key, default=None):
    return os.environ.get(f"PARAM_{key}", default)


def _screen():
    try:
        w, h = os.environ.get("DATAPULL_SCREEN", "1280x1024x24").split("x")[:2]
        return int(w), int(h)
    except Exception:
        return 1280, 1024


def main() -> int:
    login_url = _param("LOGIN_URL", "https://rcm-ga.rsmus.com:8443/login")
    username = _param("ACCOUNT_USERNAME", "")
    password = _param("ACCOUNT_PASSWORD", "")
    user_sel = _param("USERNAME_SELECTOR",
                      'input[type="email"], input[name="username" i], '
                      'input[name="user" i], input[id*="user" i], input[type="text"]')
    pass_sel = _param("PASSWORD_SELECTOR", 'input[type="password"]')
    submit_sel = _param("SUBMIT_SELECTOR",
                        'button[type="submit"], input[type="submit"], '
                        'button:has-text("Log in"), button:has-text("Sign in")')
    dwell = int(_param("DWELL_SECONDS", "60") or "60")
    out = os.environ.get("DATAPULL_OUTPUT_DIR", "/tmp/out")
    os.makedirs(out, exist_ok=True)
    width, height = _screen()

    print(f"rcm_login: opening {login_url}", flush=True)
    rc = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--window-position=0,0", f"--window-size={width},{height}",
        ])
        # Internal endpoint may use a non-public/self-signed cert.
        context = browser.new_context(ignore_https_errors=True, no_viewport=True)
        context.set_default_timeout(30000)
        page = context.new_page()
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
            print("loaded:", page.url, "|", page.title(), flush=True)
            page.screenshot(path=os.path.join(out, "login_page.png"), full_page=True)

            if username and password:
                page.locator(user_sel).first.fill(username, timeout=15000)
                page.locator(pass_sel).first.fill(password, timeout=15000)
                page.locator(submit_sel).first.click(timeout=15000)
                try:
                    page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass
                print("after submit:", page.url, "|", page.title(), flush=True)
                page.screenshot(path=os.path.join(out, "after_login.png"), full_page=True)
            else:
                print("ACCOUNT_USERNAME/ACCOUNT_PASSWORD not set — bind an account "
                      "connection. Loaded the page only.", flush=True)
                rc = 2

            print(f"dwelling {dwell}s (watch via Live view) ...", flush=True)
            time.sleep(dwell)
        except Exception as e:
            print("ERROR:", e, flush=True)
            try:
                page.screenshot(path=os.path.join(out, "error.png"), full_page=True)
            except Exception:
                pass
            rc = 1
        finally:
            try:
                browser.close()
            except Exception:
                pass
    return rc
