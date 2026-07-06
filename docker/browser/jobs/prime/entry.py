"""Job entry: build config from PARAM_* env, wire MFA to the runtime input
channel, run the Prime scraper, and leave downloads under DATAPULL_OUTPUT_DIR
(the platform registers them as run outputs)."""
import logging

from datapull_runtime import (
    EXIT_CONFIG, EXIT_FORBIDDEN, EXIT_LOGIN, EXIT_MFA, EXIT_OK, EXIT_UNEXPECTED,
    InputTimeout, get_parameter, request_input)

from jobs.prime import config, ui
from jobs.prime.browser import launch
from jobs.prime.errors import (
    LoginError, PortalForbiddenError, SessionExpiredError, dump_failure)
from jobs.prime.manifest import RunManifest
from jobs.prime.organizer import Organizer
from jobs.prime.portal import PrimePortal

log = logging.getLogger("prime")


def main() -> int:
    try:
        settings = config.load_settings()
        account = config.load_account()
        programs = config.load_programs()
        args = config.load_args()
    except Exception as e:
        ui.error(f"Configuration problem: {e}")
        return EXIT_CONFIG
    if not settings.login_url:
        ui.error("LOGIN_URL parameter is required.")
        return EXIT_CONFIG

    out_dir = config.output_dir()
    # Quarter: use a preset (QUARTER job param / resume-pinned) if present, else
    # prompt the operator; if unanswered (unattended), fall back to the portal's
    # current quarter. Just a normal runtime parameter — nothing quarter-specific.
    quarter = config.validate_quarter(get_parameter(
        "QUARTER", kind="text",
        prompt="Quarter to scrape as YYYYQ (e.g. 20261). "
               "Leave unanswered to use the portal's current quarter.",
        required=False, timeout=180))

    manifest = RunManifest(out_dir, account.username)
    organizer = Organizer(out_dir, programs)

    # MFA: ask the platform for the code. Resolved by the bound graph_mailbox
    # connection (auto) or by an operator in the UI; blocks until then.
    mfa_timeout = max(60, settings.timeouts.mfa_total_ms // 1000)

    def mfa_provider(attempt, max_attempts):
        return request_input(
            "okta_mfa",
            kind="otp",
            prompt=f"Okta email verification code (attempt {attempt}/{max_attempts})",
            timeout=mfa_timeout,
            # Poll modestly — this can wait hours for an operator, so don't hit
            # the runtime API / mailbox provider every few seconds the whole time.
            poll=15,
        )

    ui.banner()
    if args.dry_run:
        ui.warn("DRY RUN - everything is enumerated, nothing downloaded.")

    exit_code = EXIT_OK
    try:
        with launch(settings) as (context, page):
            portal = PrimePortal(context, page, settings, organizer, manifest,
                                 args, mfa_provider)
            try:
                portal.login(account)
                portal.run(quarter_override=quarter)
            except Exception:
                dump_failure(portal.page, manifest.run_dir, "fatal")
                raise
    except InputTimeout as e:
        ui.error(f"MFA was not supplied in time: {e}")
        exit_code = EXIT_MFA
    except LoginError as e:
        ui.error(f"Login failed: {e}")
        exit_code = EXIT_LOGIN
    except SessionExpiredError as e:
        ui.error(str(e))
        exit_code = EXIT_MFA
    except PortalForbiddenError as e:
        ui.error(str(e))
        exit_code = EXIT_FORBIDDEN
    except Exception as e:
        ui.error(f"Unexpected failure: {e}")
        log.exception("unexpected failure")
        exit_code = EXIT_UNEXPECTED
    finally:
        import shutil
        shutil.rmtree(manifest.run_dir / "tmp", ignore_errors=True)
        manifest.close()

    ui.summary(manifest.counts, out_dir)
    if manifest.counts.get("FAILED", 0) and exit_code == EXIT_OK:
        exit_code = EXIT_UNEXPECTED
    return exit_code
