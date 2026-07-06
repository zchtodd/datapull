"""Prime Therapeutics eInvoice portal: the iteration/download state machine.

For every Business Line x Program Name: SEARCH, then per results page:
  PDF pass:  check ALL pending rows -> Report Type 'Combined' -> CONTINUE ->
             each row's status cell gets a Download button -> click each.
  CMS pass:  Report Type 'cmsFormat' -> per row: check -> CONTINUE -> file
             STREAMS directly from CONTINUE (suggested name 'einvoice.txt').

JSF/Mojarra: dropdown changes fire AJAX partial re-renders (which clear checked
boxes), CONTINUE for CMS is AJAX too. Never cache element handles.
"""
import logging
import os
import threading
import time
from pathlib import Path

from jobs.prime import okta
from jobs.prime import selectors as SEL
from jobs.prime import ui
from jobs.prime.config import REPORT_CMS, REPORT_PDF
from jobs.prime.downloader import capture_download
from jobs.prime.errors import (
    PortalError, PortalForbiddenError, ReauthRequired, SessionExpiredError,
    dump_failure)
from jobs.prime.parsing import Combo, Option, scrape_rows

try:  # runtime reporting is best-effort and optional (absent in unit tests)
    from datapull_runtime import (
        checkpoint_done, completed_checkpoints, report_failure, set_progress,
        set_progress_total)
except Exception:  # pragma: no cover
    checkpoint_done = completed_checkpoints = report_failure = set_progress = \
        set_progress_total = None

log = logging.getLogger("prime")

REPORT_LABELS = {REPORT_PDF: "PDF", REPORT_CMS: "CMS"}


class PrimePortal:
    name = "prime"

    def __init__(self, context, page, settings, organizer, manifest, args, mfa_provider):
        self.context = context
        self.page = page
        self.settings = settings
        self.t = settings.timeouts
        self.organizer = organizer
        self.manifest = manifest
        self.args = args
        self.mfa_provider = mfa_provider
        self.temp_dir = manifest.run_dir / "tmp"
        self.throttle_ms = settings.throttle_ms
        self.download_retries = settings.download_retries
        self.search_interval_ms = settings.search_interval_ms
        self._last_search_at = 0.0  # monotonic time of the last Search submission
        self.last_dialog = None
        self.stray_downloads = []
        self.forbidden = None  # set to the URL if the portal returns 403
        self._combo_failed = False  # any row failed in the current combo?
        self._page_failed = False  # any row failed on the current results page?
        # Rows that failed on the current page this attempt, collected for the
        # in-page retry pass; only rows still failing after retries are finalized.
        self._page_failures = []
        self._await_dumps = 0  # cap on evidence dumps from a stuck await
        # Debug instrumentation: a heartbeat thread logs the current step and
        # how long we've been on it, so an indefinite hang in a blocking
        # Playwright call (e.g. a checkbox check() stalled behind a JS dialog
        # that the sync handler can't dispatch) surfaces as "STILL at <step>
        # for Ns" instead of silence. The thread only reads plain Python state
        # (_step_label / _step_since) — it never calls Playwright, which is not
        # thread-safe.
        self._step_label = "starting"
        self._step_since = time.monotonic()
        # Live view: write a screenshot of the current page to DATAPULL_LIVE_FRAME
        # every few seconds (the web serves the latest for the operator console).
        self._live_path = os.environ.get("DATAPULL_LIVE_FRAME")
        self._live_interval = max(0.5, int(
            os.environ.get("DATAPULL_LIVE_INTERVAL_MS", "2000")) / 1000)
        self._live_last = 0.0
        self._start_heartbeat()

    def _set_step(self, label):
        """Record the step we're about to (potentially) block on."""
        self._step_label = label
        self._step_since = time.monotonic()
        log.debug("STEP %s", label)
        self._snap_live()

    def _snap_live(self):
        """Best-effort live-view frame: a throttled viewport screenshot to the
        live path (atomic write). Never raises or blocks the run — a short
        timeout skips the frame if the page can't be captured right now."""
        if not self._live_path:
            return
        now = time.monotonic()
        if now - self._live_last < self._live_interval:
            return
        self._live_last = now
        try:
            tmp = self._live_path + ".tmp"
            self.page.screenshot(path=tmp, type="jpeg", quality=45, timeout=3000)
            os.replace(tmp, self._live_path)  # atomic: web never reads a half-written frame
        except Exception:
            pass

    def _pace(self):
        """Throttle before a server-hitting action so we don't overload the
        portal. Tunable via the THROTTLE_MS job parameter (0 disables)."""
        if self.throttle_ms > 0:
            time.sleep(self.throttle_ms / 1000)

    def _start_heartbeat(self, every=10.0, warn_after=8.0):
        def beat():
            while True:
                time.sleep(every)
                elapsed = time.monotonic() - self._step_since
                if elapsed >= warn_after:
                    log.warning("HEARTBEAT still at %r for %.0fs",
                                self._step_label, elapsed)
        threading.Thread(target=beat, name="prime-heartbeat", daemon=True).start()

    def _safe_is_checked(self, locator):
        """is_checked() that returns a marker string instead of blocking/raising,
        so it's safe to call purely for logging."""
        try:
            return locator.is_checked(timeout=2000)
        except Exception as e:
            return f"?({e.__class__.__name__})"

    def _inventory_controls(self, row):
        """When a row's outcome never appears, dump what's actually on the page
        — every button/input value (incl. disabled) and link text, the tab
        count, and a screenshot+HTML — so we can see what control the portal
        offers for a single Combined-PDF invoice."""
        try:
            data = self.page.evaluate(
                """() => {
                    const txt = el => (el.value || el.textContent || '').trim();
                    const btns = [...document.querySelectorAll(
                        'input[type=button],input[type=submit],input[type=image],button')]
                        .map(e => ({v: txt(e), disabled: !!e.disabled})).slice(0, 80);
                    const links = [...document.querySelectorAll('a')]
                        .map(e => (e.textContent || '').trim()).filter(Boolean).slice(0, 80);
                    return {btns, links};
                }"""
            )
            log.warning("await INVENTORY %s: url=%s tabs=%d buttons=%s links=%s",
                        row.invoice_no, self.page.url, len(self.context.pages),
                        data.get("btns"), data.get("links"))
        except Exception as e:
            log.warning("await INVENTORY %s: evaluate failed: %s", row.invoice_no, e)
        if self._await_dumps < 3:
            self._await_dumps += 1
            try:
                dump_failure(self.page, self.manifest.run_dir,
                             f"await_{row.invoice_no}")
            except Exception as e:
                log.warning("await dump failed: %s", e)

    # ------------------------------------------------------------- login
    def login(self, account):
        self.account = account  # kept for mid-run re-authentication
        okta.login(self.page, account, self.settings, self.mfa_provider,
                   evidence_dir=self.manifest.run_dir, snap=self._snap_live)
        self._open_einvoice()

    def _reauthenticate(self):
        """Recover from a mid-run Okta bounce: re-authenticate (which dispatches
        a fresh MFA request for the operator/mailbox to supply) and reopen the
        eInvoice app + search form. The caller then retries the work in flight."""
        okta.reauthenticate(self.page, self.account, self.settings,
                            self.mfa_provider, evidence_dir=self.manifest.run_dir,
                            snap=self._snap_live)
        self._open_einvoice()

    def _open_einvoice(self):
        ui.step("Opening the eInvoice application ...")
        tile = self.page.locator(SEL.EINVOICE_TILE).first
        tile.wait_for(state="visible", timeout=self.t.default_ms)
        try:
            with self.context.expect_page(timeout=8000) as new_page_info:
                tile.click()
            self.page = new_page_info.value
            self.page.wait_for_load_state("domcontentloaded")
            log.debug("eInvoice opened in a new tab: %s", self.page.url)
        except Exception:
            log.debug("eInvoice opened in the same tab: %s", self.page.url)

        def _on_dialog(d):
            # Log BEFORE accepting and include the type — alert vs confirm vs
            # beforeunload matter. If this never logs while we're hung on a
            # click/check, the dialog deadlocked the sync handler.
            log.warning("js dialog opened: type=%s message=%r", d.type, d.message)
            self.last_dialog = d.message
            try:
                d.accept()
                log.debug("js dialog accepted")
            except Exception as e:
                log.warning("js dialog accept() failed: %s", e)

        def _on_download(d):
            log.debug("download event: suggested=%r url=%s",
                      d.suggested_filename, d.url)
            self.stray_downloads.append(d)

        def _on_response(resp):
            # A 403 on a navigation or AJAX postback means the portal blocked us
            # (rate-limited / access denied). Record it; _check_session turns it
            # into a fatal error instead of letting the run hang waiting for
            # elements that will never render. (Plain function — Playwright sync
            # chokes on builtin methods as handlers.)
            try:
                if resp.status == 403 and resp.request.resource_type in (
                        "document", "xhr", "fetch"):
                    self.forbidden = resp.url
                    log.error("portal returned 403 Forbidden: %s", resp.url)
            except Exception:
                pass

        self.page.on("dialog", _on_dialog)
        self.page.on("download", _on_download)
        self.page.on("response", _on_response)
        self._goto_search_form()

    def _goto_search_form(self):
        try:
            self.page.locator(SEL.BUSINESS_LINE_SELECT).first.wait_for(
                state="visible", timeout=8000)
            return
        except Exception:
            pass
        log.debug("search form not visible, navigating Invoices > Search")
        self.page.locator(SEL.INVOICES_TAB).first.click()
        self._settle({"form": SEL.BUSINESS_LINE_SELECT, "subnav": SEL.SEARCH_SUBNAV})
        if not self._visible(SEL.BUSINESS_LINE_SELECT):
            self.page.locator(SEL.SEARCH_SUBNAV).first.click()
            self._settle({"form": SEL.BUSINESS_LINE_SELECT})

    # Give up (fail the run) if one program needs more re-auths than this —
    # signals the session can't be kept alive rather than a transient bounce.
    MAX_REAUTHS_PER_COMBO = 3

    # --------------------------------------------------------------- run
    def run(self, quarter_override=None):
        # Enumerate every business line x program up front so progress has a
        # fixed denominator (one unit = one combo), then work through them.
        combos = self._enumerate_combos()
        self._report_total(len(combos))
        # Skip programs already completed for this quarter in an earlier run or
        # resume. Completion is recorded as a checkpoint keyed by quarter
        # (namespace) + "business line||program"; a done program is skipped
        # entirely — no search, no scrape. A partially-done program is entered
        # but skips its already-completed results pages (finer-grained page
        # checkpoints, "business line||program||p<n>"), so resume doesn't re-walk
        # pages it already finished — see _run_combo.
        namespace = quarter_override or self._current_quarter()
        done = set(completed_checkpoints(namespace=namespace) or []) \
            if (namespace and completed_checkpoints) else set()
        if done:
            log.info("%d program(s) already completed for quarter %s; will skip",
                     len(done), namespace)
        for i, (bl, prog) in enumerate(combos, 1):
            key = f"{bl.label}||{prog.label}"
            if namespace and key in done:
                ui.info(f"skipping completed program: {bl.label} / {prog.label}")
                self._report_progress(i, f"{bl.label} / {prog.label} (already done)")
                continue
            self._report_progress(i - 1, f"{bl.label} / {prog.label}")
            self._combo_failed = False
            reauths = 0
            while True:
                try:
                    self._run_combo(bl, prog, quarter_override, namespace, done)
                except ReauthRequired as e:
                    reauths += 1
                    if reauths > self.MAX_REAUTHS_PER_COMBO:
                        raise SessionExpiredError(
                            f"re-authentication didn't stabilize the session after "
                            f"{self.MAX_REAUTHS_PER_COMBO} attempts: {e}")
                    ui.warn(f"Re-auth needed mid-program ({bl.label} / {prog.label}); "
                            f"requesting a new MFA code (attempt {reauths})")
                    self._reauthenticate()
                    continue  # retry this program; its finished invoices are skipped
                except (SessionExpiredError, PortalForbiddenError):
                    raise
                except Exception as e:
                    log.exception("combo failed: %s / %s", bl.label, prog.label)
                    dump_failure(self.page, self.manifest.run_dir,
                                 f"combo_{bl.label}_{prog.label}")
                    self.manifest.record(
                        "FAILED",
                        combo=Combo(bl.label, prog.label, quarter_override or ""),
                        error=f"combo-level failure: {e}")
                    ui.error(f"Combo failed, continuing: {bl.label} / {prog.label}: {e}")
                    self._recover(bl, prog, quarter_override)
                    break
                else:
                    # Record done only if no row failed, so a partially-failed
                    # program is retried next time (its finished rows skipped by
                    # the existing-file check) rather than skipped wholesale.
                    if namespace and not self._combo_failed and checkpoint_done:
                        checkpoint_done(key, namespace=namespace)
                    break
            self._report_progress(i, f"{bl.label} / {prog.label}")

    def _current_quarter(self):
        """The search form's Year Qtr default (YYYYQ), used as the checkpoint
        namespace so completion is tracked per quarter. Best-effort; '' if
        unreadable (which simply disables skip — the run proceeds normally)."""
        try:
            v = self.page.locator(SEL.YEAR_QTR_INPUT).first.input_value(timeout=2000).strip()
            return v if len(v) == 5 and v.isdigit() else ""
        except Exception:
            return ""

    def _enumerate_combos(self):
        """Build the full list of (business line, program) combos to process,
        applying the only_* filters — used as the progress denominator."""
        combos = []
        for bl in self._options(SEL.BUSINESS_LINE_SELECT):
            if self.args.only_business_line and bl.label != self.args.only_business_line:
                continue
            self._select_settle(SEL.BUSINESS_LINE_SELECT, bl.value)
            programs = self._options(SEL.PROGRAM_SELECT)
            log.info("business line %r: %d programs", bl.label, len(programs))
            for prog in programs:
                if self.args.only_program and prog.label != self.args.only_program:
                    continue
                combos.append((bl, prog))
        log.info("enumerated %d combo(s) to process", len(combos))
        return combos

    def _report_total(self, n):
        if set_progress_total:
            set_progress_total(n, message="Starting…")

    def _report_progress(self, done, message):
        if set_progress:
            set_progress(done, message=message)

    def _run_combo(self, bl, prog, quarter_override, namespace=None, done=None):
        self._set_step(f"combo {bl.label} / {prog.label}: select")
        self._select_settle(SEL.BUSINESS_LINE_SELECT, bl.value)
        self._select_settle(SEL.PROGRAM_SELECT, prog.value)
        year_qtr = self._apply_quarter(quarter_override)
        combo = Combo(bl.label, prog.label, year_qtr)
        ui.step(f"Searching: {bl.label} / {prog.label} / {year_qtr}")
        log.debug("combo %s / %s / %s: searching", bl.label, prog.label, year_qtr)

        if self._search() == "empty":
            self.manifest.record("EMPTY_COMBO", combo=combo)
            ui.info("no invoices for this combination")
            return

        # Page-level resume: skip pages already finished (in a prior run or
        # earlier in this one) and checkpoint each page as it completes cleanly.
        # Disabled when a row cap is set (a debug knob whose "first N rows"
        # semantics don't mix with skipping pages).
        use_ckpt = bool(namespace) and not self.args.max_rows
        processed = 0
        for page_no in self._page_numbers():
            if self.args.max_rows and processed >= self.args.max_rows:
                break
            page_key = f"{bl.label}||{prog.label}||p{page_no}"
            if use_ckpt and done is not None and page_key in done:
                ui.info(f"page {page_no}: already completed, skipping")
                continue
            self._page_failed = False
            self._page_failures = []
            self._goto_page(page_no)
            rows = scrape_rows(self.page, SEL.RESULTS_ROW, page_no)
            if not rows:
                raise PortalError(f"results page {page_no} scraped no data rows "
                                  "(selector mismatch? see saved HTML)")
            if self.args.max_rows:
                rows = rows[: self.args.max_rows - processed]
            processed += len(rows)
            ui.info(f"page {page_no}: {len(rows)} invoice row(s)")
            self._page_pass_pdf(combo, rows, page_no)
            self._page_pass_cms(combo, rows, page_no)
            self._retry_page_failures(combo, page_no)
            # Record the page done only if no row on it failed, so a page with a
            # failure is re-walked next time (its finished rows skipped by the
            # existing-file check) rather than skipped wholesale.
            if use_ckpt and not self._page_failed and checkpoint_done:
                checkpoint_done(page_key, namespace=namespace)
                if done is not None:
                    done.add(page_key)

    def _retry_page_failures(self, combo, page_no):
        """Re-attempt the invoices that failed on this page, up to
        `download_retries` times, each with a fresh Search so a stale grid or a
        transient portal hiccup can clear. Only rows still failing after the
        retries are finalized (recorded + reported), which also lets a page whose
        failures were transient still be checkpointed as done."""
        attempt = 0
        while self._page_failures and attempt < self.download_retries:
            attempt += 1
            pending = self._page_failures
            self._page_failures = []
            pdf_rows = [row for (row, rt, exc) in pending if rt == REPORT_PDF]
            cms_rows = [row for (row, rt, exc) in pending if rt == REPORT_CMS]
            ui.warn(f"retrying {len(pending)} failed download(s) on page {page_no} "
                    f"(attempt {attempt}/{self.download_retries}) ...")
            self._pace()
            self._search()  # fresh grid
            if pdf_rows:
                self._page_pass_pdf(combo, pdf_rows, page_no)
            if cms_rows:
                self._page_pass_cms(combo, cms_rows, page_no)
        # Whatever still failed after the retries is a real failure now.
        for row, report_type, exc in self._page_failures:
            self._finalize_failure(combo, row, report_type, exc)
        self._page_failures = []

    # ------------------------------------------------------ per-page passes
    def _split_pending(self, combo, rows, report_type):
        label = REPORT_LABELS[report_type]
        pending = []
        for idx, row in enumerate(rows, 1):
            existing = self.organizer.existing_file(combo, row, report_type)
            if existing:
                self.manifest.record("SKIPPED_EXISTS", combo=combo, row=row,
                                     report_type=report_type, file_path=existing)
                ui.progress(combo, label, idx, len(rows), row.invoice_no,
                            "already downloaded")
            elif self.args.dry_run:
                target = self.organizer.target_path(combo, row, report_type)
                self.manifest.record("WOULD_DOWNLOAD", combo=combo, row=row,
                                     report_type=report_type, file_path=target)
                ui.progress(combo, label, idx, len(rows), row.invoice_no,
                            "would download (dry run)")
            else:
                pending.append(row)
        return pending

    # Combined-PDF reports generate asynchronously. The portal only accepts a
    # SINGLE checked invoice per CONTINUE, and a kicked-off ("In Progress") row
    # does NOT update in place — its Download button only appears after the grid
    # is refreshed, which happens on the next CONTINUE or by re-running Search.
    # So we can't wait on a row in place; we pipeline: kick each invoice off,
    # harvest whatever's ready after each refresh, then drain the tail by
    # re-querying. A ready row shows a Download button (and keeps its checkbox).
    PDF_DRAIN_STALE_ROUNDS = 3   # give up after this many no-progress refreshes

    def _page_pass_pdf(self, combo, rows, page_no):
        pending = self._split_pending(combo, rows, REPORT_PDF)
        if not pending:
            return
        remaining = {r.invoice_no: r for r in pending}  # not yet resolved
        done = set()

        # Phase 1 — kick off each invoice (check one, CONTINUE), harvesting any
        # rows that became ready on the refresh that CONTINUE triggered.
        for idx, row in enumerate(pending, 1):
            if row.invoice_no not in remaining:
                continue  # already harvested as a side effect of an earlier refresh
            try:
                self._goto_page(page_no)
                self._set_report_type(REPORT_PDF)  # re-assert (refresh resets it)
                self._check_row(row)
                self._continue_and_settle()        # kick off + ack + grid refresh
            except (SessionExpiredError, PortalForbiddenError, ReauthRequired):
                raise
            except Exception as e:
                self._note_failure(combo, row, REPORT_PDF, e, idx, len(pending))
                remaining.pop(row.invoice_no, None)
                done.add(row.invoice_no)
                continue
            self._harvest_ready(combo, remaining, done, page_no, len(pending))

        # Phase 2 — drain: the last kicked-off reports have no further CONTINUE
        # to reveal them, so re-run Search to refresh statuses and harvest until
        # everything resolves or we stop making progress.
        deadline = time.monotonic() + self.t.download_ms / 1000
        stale = 0
        while remaining and stale < self.PDF_DRAIN_STALE_ROUNDS \
                and time.monotonic() < deadline:
            time.sleep(2)  # let in-flight reports finish generating
            try:
                self._refresh_grid()
            except (SessionExpiredError, PortalForbiddenError, ReauthRequired):
                raise
            except Exception as e:
                log.debug("drain refresh failed: %s", e)
            before = len(done)
            self._harvest_ready(combo, remaining, done, page_no, len(pending))
            stale = 0 if len(done) > before else stale + 1

        # Whatever's left never produced a report in time.
        for inv, row in list(remaining.items()):
            self._note_failure(combo, row, REPORT_PDF,
                             PortalError("report never became ready (timed out)"),
                             len(pending), len(pending))
            remaining.pop(inv, None)

    def _harvest_ready(self, combo, remaining, done, page_no, total):
        """Scan the current grid; capture any not-yet-resolved invoice that now
        shows a Download button, and mark 'No Invoice Data' rows resolved too."""
        if not remaining:
            return
        self._goto_page(page_no)
        for inv in list(remaining.keys()):
            row = remaining[inv]
            try:
                row_loc = self._row_locator(inv)
            except PortalError:
                continue  # not on this page right now
            if row_loc.locator(SEL.ROW_NO_DATA).count() > 0:
                self._record_outcome(combo, row, REPORT_PDF, "nodata", None,
                                     len(done) + 1, total)
                done.add(inv); remaining.pop(inv, None)
                continue
            buttons = row_loc.locator(SEL.ROW_DOWNLOAD_BTN)
            if buttons.count() == 0:
                continue  # still generating
            self._set_step(f"harvest {inv}")
            try:
                self._record_outcome(combo, row, REPORT_PDF, "button", buttons,
                                     len(done) + 1, total)
            except (SessionExpiredError, PortalForbiddenError, ReauthRequired):
                raise
            except Exception as e:
                self._note_failure(combo, row, REPORT_PDF, e, len(done) + 1, total)
            done.add(inv); remaining.pop(inv, None)

    def _refresh_grid(self):
        """Re-run the current Search to re-render the grid with up-to-date report
        statuses — the only way the final In-Progress rows reveal a Download
        button once there's no further CONTINUE to trigger it."""
        self._set_step("refresh grid (re-search)")
        log.debug("draining: re-running Search to refresh report statuses")
        self._search()

    def _page_pass_cms(self, combo, rows, page_no):
        pending = self._split_pending(combo, rows, REPORT_CMS)
        if not pending:
            return
        self._set_report_type(REPORT_CMS)
        for idx, row in enumerate(pending, 1):
            try:
                self._goto_page(page_no)
                self._check_row(row)
                self.stray_downloads.clear()
                self._continue_and_settle()
                kind, payload = self._await_row_outcome(row, prefer_stray=True)
                self._record_outcome(combo, row, REPORT_CMS, kind, payload,
                                     idx, len(pending))
            except (SessionExpiredError, PortalForbiddenError, ReauthRequired):
                raise
            except Exception as e:
                self._note_failure(combo, row, REPORT_CMS, e, idx, len(pending))

    # --------------------------------------------------- per-row mechanics
    def _check_row(self, row):
        inv = row.invoice_no
        self._set_step(f"check_row {inv}: locate")
        row_loc = self._row_locator(inv)
        cb = row_loc.locator(SEL.ROW_CHECKBOX).first
        log.debug("check_row %s: checked-before=%s; calling check()",
                  inv, self._safe_is_checked(cb))
        self._set_step(f"check_row {inv}: initial check()")
        cb.check(timeout=self.t.default_ms)
        log.debug("check_row %s: initial check() returned", inv)
        time.sleep(0.3)
        for attempt in range(1, 4):
            cb = self._row_locator(inv).locator(SEL.ROW_CHECKBOX).first
            self._set_step(f"check_row {inv}: verify #{attempt}")
            checked = self._safe_is_checked(cb)
            log.debug("check_row %s: verify #%d checked=%s", inv, attempt, checked)
            if checked is True:
                self._set_step(f"check_row {inv}: checked OK")
                return
            log.debug("checkbox for %s was cleared; re-checking (attempt %d)",
                      inv, attempt)
            self._set_step(f"check_row {inv}: re-check #{attempt} check()")
            cb.check(timeout=self.t.default_ms)
            log.debug("check_row %s: re-check #%d returned", inv, attempt)
            time.sleep(0.5)
        raise PortalError(f"checkbox for {inv} would not stay checked")

    def _set_report_type(self, report_type):
        self._set_step(f"set_report_type {REPORT_LABELS.get(report_type, report_type)}")
        log.debug("set_report_type: selecting %r", report_type)
        self._pace()
        self.page.locator(SEL.REPORT_TYPE_SELECT).first.select_option(
            value=SEL.REPORT_TYPE_VALUES[report_type], timeout=self.t.default_ms)
        log.debug("set_report_type: selected, waiting for ajax")
        self._wait_ajax()
        log.debug("set_report_type: ajax settled")

    def _continue_and_settle(self):
        self.last_dialog = None
        self._set_step("continue: click CONTINUE")
        log.debug("continue: clicking CONTINUE")
        self._pace()
        self.page.locator(SEL.CONTINUE_BUTTON).first.click(timeout=self.t.default_ms)
        log.debug("continue: clicked, settling")
        self._set_step("continue: settle")
        self._settle({"results": SEL.RESULTS_TABLE})
        log.debug("continue: settled (last_dialog=%r)", self.last_dialog)
        if self.last_dialog and "no invoice" in self.last_dialog.lower():
            raise PortalError(f"portal rejected CONTINUE: {self.last_dialog!r}")
        # The portal holds the file until a SECOND Continue — on an
        # acknowledgment screen ("...acknowledging receipt of invoice data") — is
        # clicked. It can sit at the bottom of the still-visible results page, so
        # check the marker explicitly rather than trusting which sentinel settled.
        if self._visible(SEL.ACK_RECEIPT_MARKER):
            self._acknowledge_receipt()

    def _acknowledge_receipt(self):
        log.debug("acknowledgment screen present; clicking Continue to release file")
        self._set_step("continue: acknowledge receipt")
        self._pace()
        self.page.locator(SEL.ACK_CONTINUE).first.click(timeout=self.t.default_ms)
        self._set_step("continue: settle after ack")
        try:
            self._settle({"results": SEL.RESULTS_TABLE}, timeout_ms=8000)
        except PortalError:
            # Acknowledging may stream the file without returning to the results
            # table; the download handler captures it as a stray and
            # _await_row_outcome picks it up.
            log.debug("post-ack: results not back (file likely streamed)")

    def _await_row_outcome(self, row, prefer_stray):
        self._set_step(f"await_outcome {row.invoice_no} (prefer_stray={prefer_stray})")
        deadline = time.monotonic() + self.t.download_ms / 1000
        loops = 0
        while time.monotonic() < deadline:
            loops += 1
            self._check_session()
            if prefer_stray and self.stray_downloads:
                return "stray", self.stray_downloads.pop(0)
            row_loc = self._row_locator(row.invoice_no)
            if row_loc.locator(SEL.ROW_NO_DATA).count() > 0:
                return "nodata", None
            buttons = row_loc.locator(SEL.ROW_DOWNLOAD_BTN)
            if buttons.count() > 0:
                return "button", buttons
            if self.stray_downloads:
                return "stray", self.stray_downloads.pop(0)
            if loops % 20 == 0:  # ~ every 10s
                log.debug("await_outcome %s: still waiting (%.0fs, strays=%d)",
                          row.invoice_no, loops * 0.5, len(self.stray_downloads))
            if loops == 16:  # ~8s in: capture what the portal actually shows
                self._inventory_controls(row)
            time.sleep(0.5)
        raise PortalError("row never showed a Download button, 'No Invoice Data', "
                          f"or a direct download within {self.t.download_ms // 1000}s")

    def _record_outcome(self, combo, row, report_type, kind, payload, idx, total):
        label = REPORT_LABELS[report_type]
        if kind == "nodata":
            self.manifest.record("NO_DATA", combo=combo, row=row,
                                 report_type=report_type)
            ui.progress(combo, label, idx, total, row.invoice_no, "no invoice data")
            return
        if kind == "stray":
            suggested = payload.suggested_filename or "einvoice.txt"
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = self.temp_dir / f"{int(time.time() * 1000)}_{suggested}"
            # save_as() blocks until the download fully completes, with NO
            # timeout — a stalled stream hangs here forever.
            self._set_step(f"save stray {row.invoice_no} -> {suggested}")
            log.debug("record_outcome %s: saving stray download", row.invoice_no)
            payload.save_as(str(temp_path))
            log.debug("record_outcome %s: stray saved", row.invoice_no)
        else:  # button
            self.stray_downloads.clear()
            self._set_step(f"capture button download {row.invoice_no}")
            log.debug("record_outcome %s: clicking download button", row.invoice_no)
            self._pace()
            temp_path, suggested = capture_download(
                self.page, lambda: payload.first.click(),
                self.temp_dir, self.t.download_ms)
            log.debug("record_outcome %s: button download captured", row.invoice_no)
            self.stray_downloads.clear()
        ext = Path(suggested).suffix or None
        target = self.organizer.target_path(combo, row, report_type,
                                            suggested_ext=ext)
        self.organizer.place(temp_path, target)
        self.manifest.record("DOWNLOADED", combo=combo, row=row,
                             report_type=report_type, file_path=target,
                             suggested_name=suggested)
        ui.progress(combo, label, idx, total, row.invoice_no, "downloaded")

    def _note_failure(self, combo, row, report_type, exc, idx, total):
        """Soft failure: queue the row for this page's retry pass instead of
        finalizing it. Only rows still failing after the retries become real
        failures (see _finalize_failure)."""
        label = REPORT_LABELS[report_type]
        log.warning("row download failed (will retry if attempts remain): %s %s: %s",
                    row.invoice_no, label, exc)
        self._page_failures.append((row, report_type, exc))
        ui.progress(combo, label, idx, total, row.invoice_no, "failed (will retry)")

    def _finalize_failure(self, combo, row, report_type, exc):
        """Record a row as a real failure after retries are exhausted: mark the
        page/combo failed (so neither is checkpointed), capture evidence, and
        surface it via the manifest + the platform failure feed."""
        self._combo_failed = True  # so this combo isn't checkpointed as done
        self._page_failed = True   # nor this page (its row checkpoint is withheld)
        label = REPORT_LABELS[report_type]
        log.error("row failed after retries: %s %s: %s",
                  row.invoice_no, label, exc)
        base = dump_failure(self.page, self.manifest.run_dir,
                            f"row_{row.invoice_no}_{label}")
        self.manifest.record("FAILED", combo=combo, row=row,
                             report_type=report_type, error=str(exc))
        # Surface it as a first-class failure so operators see which invoices
        # need chasing, with a link to the captured screenshot.
        if report_failure:
            report_failure(item=row.invoice_no, kind=label,
                           label=f"{combo.business_line} / {combo.program}",
                           detail=str(exc), evidence=f"{base.name}.png")
        ui.warn(f"{label} {row.invoice_no}: FAILED after "
                f"{self.download_retries} retr{'y' if self.download_retries == 1 else 'ies'}")

    # ------------------------------------------------------ search state
    def _search(self):
        self._set_step("search: click Search")
        self._pace_search()
        self.page.locator(SEL.SEARCH_BUTTON).first.click(timeout=self.t.default_ms)
        self._last_search_at = time.monotonic()
        self._set_step("search: settle")
        outcome = self._settle({"results": SEL.RESULTS_TABLE, "empty": SEL.NO_RECORDS})
        log.debug("search settled: %s", outcome)
        return outcome

    def _pace_search(self):
        """Space consecutive Search submissions by at least search_interval_ms
        (measured submission-to-submission). Submitting Search too fast back-to-
        back — as when sweeping an empty quarter where every combo returns no
        records and settles instantly — trips a portal 403, so floor the rate
        here regardless of how quickly results settle. Searches already separated
        by real download work incur no extra wait. The normal per-action throttle
        still applies on top."""
        if self.search_interval_ms > 0 and self._last_search_at:
            remaining = self.search_interval_ms / 1000 - (time.monotonic() - self._last_search_at)
            if remaining > 0:
                self._set_step(f"search: spacing {remaining:.1f}s to avoid a 403")
                time.sleep(remaining)
        self._pace()

    def _recover(self, bl, prog, quarter_override):
        try:
            self._goto_search_form()
        except Exception as e:
            log.error("recovery failed: %s", e)

    def _apply_quarter(self, override):
        inp = self.page.locator(SEL.YEAR_QTR_INPUT).first
        if override:
            inp.fill(override)
            return override
        value = inp.input_value().strip()
        if not (len(value) == 5 and value.isdigit()):
            raise PortalError(f"Year Qtr field has unexpected value {value!r}")
        return value

    def _page_numbers(self):
        if not self._visible(SEL.JUMP_PAGE_SELECT):
            return [1]
        opts = self._options(SEL.JUMP_PAGE_SELECT, skip_filter=False)
        nums = [int(o.label) for o in opts if o.label.strip().isdigit()]
        return sorted(set(nums)) or [1]

    def _goto_page(self, page_no):
        if page_no == 1 and not self._visible(SEL.JUMP_PAGE_SELECT):
            return
        if self._current_page_number() == page_no:
            return
        self._select_settle(SEL.JUMP_PAGE_SELECT, label=str(page_no))

    def _current_page_number(self):
        try:
            sel = self.page.locator(SEL.JUMP_PAGE_SELECT).first
            value = sel.input_value(timeout=2000).strip()
            return int(value) if value.isdigit() else 1
        except Exception:
            return 1

    # ------------------------------------------------------------ helpers
    def _options(self, selector, skip_filter=True):
        loc = self.page.locator(selector).first
        loc.wait_for(state="visible", timeout=self.t.default_ms)
        raw = loc.evaluate(
            "el => Array.from(el.options).map(o => ({value: o.value, label: o.label || o.text}))")
        options = [Option(o["value"], o["label"].strip()) for o in raw]
        if skip_filter:
            skip = set(self.settings.skip_option_labels)
            options = [o for o in options
                       if o.label.strip().lower() not in skip and o.value.strip() != ""]
        return options

    def _select_settle(self, selector, value=None, label=None):
        self._pace()
        loc = self.page.locator(selector).first
        if label is not None:
            loc.select_option(label=label)
        else:
            loc.select_option(value=value)
        self._wait_ajax()

    def _wait_ajax(self):
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(0.4)
        self._check_session()

    def _settle(self, sentinels, timeout_ms=None):
        try:
            self.page.wait_for_load_state("load", timeout=5000)
        except Exception:
            pass
        deadline = time.monotonic() + (timeout_ms or self.t.postback_ms) / 1000
        while time.monotonic() < deadline:
            self._check_session()
            for name, sel in sentinels.items():
                if self._visible(sel):
                    return name
            time.sleep(0.3)
        raise PortalError(f"timed out waiting for {list(sentinels)} (url: {self.page.url})")

    def _check_session(self):
        if self.forbidden:
            raise PortalForbiddenError(
                f"The portal returned 403 Forbidden ({self.forbidden}) — blocked "
                "or access denied. Stopping the run.")
        # An Okta sign-in / MFA screen mid-run means the session dropped or the
        # portal wants step-up MFA. Recover in place (re-auth + retry) rather
        # than failing the whole run.
        for marker in SEL.REAUTH_MARKERS:
            if self._visible(marker):
                raise ReauthRequired(f"portal bounced back to Okta ({marker})")

    def _visible(self, selector):
        try:
            return self.page.locator(selector).first.is_visible(timeout=200)
        except Exception:
            return False

    def _row_locator(self, invoice_no):
        loc = self.page.locator(SEL.RESULTS_ROW).filter(has_text=invoice_no)
        if loc.count() == 0:
            raise PortalError(f"row {invoice_no} not found in the current results page")
        return loc.first
