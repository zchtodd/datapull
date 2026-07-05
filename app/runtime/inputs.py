"""The runtime input channel: how a running job asks the platform for a value
it can't compute itself (an MFA code, a prompt answer), and how the platform
resolves it — via an automated provider and/or an operator typing it in the UI.

`wait_for_input` is the blocking call the job runner uses; operators resolve the
same request out-of-band through the fulfill API. Both sides meet in the DB.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import JobInputRequest, JobRun
from app.models.job_input_request import CANCELLED, EXPIRED, FULFILLED, PENDING
from app.runtime.providers import GraphMailboxOtpProvider, ProviderError
from app.services import connection_config

log = logging.getLogger("datapull.runtime")

# How many inbox reads to attempt before giving up on automated retrieval and
# revealing the manual entry box to the operator. At the SDK's ~15s poll cadence
# the default (8) gives automated retrieval roughly two minutes before a human
# is asked. Auto-retrieval also stops on the first provider error.
MFA_AUTO_MAX_ATTEMPTS = int(os.environ.get("DATAPULL_MFA_AUTO_MAX_ATTEMPTS", "8"))


class InputUnavailable(Exception):
    """Raised when an input couldn't be obtained (timeout or cancellation)."""


def auto_exhausted(r: JobInputRequest) -> bool:
    """True once automated retrieval has given up — it errored or ran out of
    attempts. No further inbox reads happen after this."""
    return r.auto_failed or r.auto_attempts >= MFA_AUTO_MAX_ATTEMPTS


def manual_ready(r: JobInputRequest) -> bool:
    """Whether the operator should be shown the manual entry box: automated
    retrieval was never an option, or it has given up."""
    return not r.auto_enabled or auto_exhausted(r)


def serialize_input_request(r: JobInputRequest) -> dict:
    """For the operator UI. Never includes the supplied value."""
    return {
        "id": r.id,
        "job_run_id": r.job_run_id,
        "name": r.name,
        "kind": r.kind,
        "prompt": r.prompt,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        # Automated-retrieval state, so the UI can show a "retrieving
        # automatically" status and only reveal the manual box once it's moot.
        "auto_enabled": r.auto_enabled,
        "auto_attempts": r.auto_attempts,
        "auto_max_attempts": MFA_AUTO_MAX_ATTEMPTS,
        "auto_failed": r.auto_failed,
        "manual_ready": manual_ready(r),
        "auto_in_progress": r.is_open and r.auto_enabled and not auto_exhausted(r),
    }


def open_request(job_run_id, name, kind="text", prompt="") -> JobInputRequest:
    req = JobInputRequest(
        job_run_id=job_run_id, name=name, kind=kind, prompt=prompt, status=PENDING
    )
    # Record up front whether automated retrieval is even possible for this
    # request (a ready OTP provider bound to the run), so the UI knows to show
    # the "retrieving automatically" phase rather than the manual box.
    job_run = db.session.get(JobRun, job_run_id)
    req.auto_enabled = job_run is not None and _auto_provider(job_run, req) is not None
    db.session.add(req)
    db.session.commit()
    return req


def fulfill(req: JobInputRequest, value: str, source: str) -> JobInputRequest:
    req.value = value
    req.source = source
    req.status = FULFILLED
    req.resolved_at = datetime.now(timezone.utc)
    db.session.commit()
    return req


def _close(req: JobInputRequest, status: str) -> None:
    req.status = status
    req.resolved_at = datetime.now(timezone.utc)
    db.session.commit()


def _auto_provider(job_run: JobRun, request: JobInputRequest):
    """Build a ready automated provider for this request, or None.

    Resolves the connection bound to the run's `mfa` role (the snapshot, so
    runtime overrides are honored).
    """
    if request.kind != "otp":
        return None
    conn = next((jrc.connection for jrc in job_run.connections
                 if jrc.connection.is_mfa), None)
    if conn is None:
        return None
    provider = GraphMailboxOtpProvider(connection_config(conn))
    return provider if provider.ready() else None


def try_auto_resolve(request: JobInputRequest) -> bool:
    """One best-effort automated-provider attempt on an open request.

    Called from the runtime poll endpoint, so resolution happens at the SDK's
    polling cadence without a background worker. Returns True if it fulfilled.

    Bounded: stops reading the inbox after MFA_AUTO_MAX_ATTEMPTS reads or the
    first provider error, after which the operator is asked for the code.
    """
    if not request.is_open or auto_exhausted(request):
        return False
    provider = _auto_provider(request.job_run, request)
    if provider is None:
        return False
    # Count this inbox read before performing it, and commit so the operator UI
    # (a different process) sees the attempt count climb tick by tick.
    request.auto_attempts += 1
    db.session.commit()
    base = request.created_at or datetime.now(timezone.utc)
    since = base - timedelta(seconds=90)
    try:
        value = provider.fetch_since(since)
    except ProviderError as e:
        log.error("auto provider failed; revealing manual entry: %s", e)
        request.auto_failed = True
        request.auto_last_error = str(e)
        db.session.commit()
        return False
    if not value:
        return False
    # Re-check under fresh state so we don't clobber a concurrent fulfillment.
    db.session.refresh(request)
    if request.is_open:
        fulfill(request, value, source="mailbox")
        return True
    return False


def wait_for_input(
    job_run_id, name, kind="text", prompt="", timeout_s=300, poll_s=4
) -> str:
    """Open an input request and block until it's fulfilled, or raise
    InputUnavailable on timeout/cancellation.

    Resolution races two sources: an automated provider (polled here) and an
    operator who fulfills the request through the API (seen via DB refresh).
    Called from the job runner inside the Flask app context.
    """
    job_run = db.session.get(JobRun, job_run_id)
    if job_run is None:
        raise InputUnavailable(f"no such job run {job_run_id}")

    request = open_request(job_run_id, name, kind, prompt)
    provider = _auto_provider(job_run, request)
    # Look slightly before the request to catch a code that just arrived.
    since = datetime.now(timezone.utc) - timedelta(seconds=90)
    deadline = time.monotonic() + timeout_s
    log.info(
        "input %r opened for run %s (auto provider: %s)",
        name, job_run_id, type(provider).__name__ if provider else "none",
    )

    while time.monotonic() < deadline:
        # An operator (different process) may have fulfilled/cancelled it.
        db.session.refresh(request)
        if request.status == FULFILLED:
            return request.value
        if request.status == CANCELLED:
            raise InputUnavailable(f"input {name!r} was cancelled")

        # Auto-retrieval is bounded: stop after the attempt cap or the first
        # error, then fall through to operator-only (manual box revealed in UI).
        if provider is not None and not auto_exhausted(request):
            request.auto_attempts += 1
            db.session.commit()
            try:
                value = provider.fetch_since(since)
            except ProviderError as e:
                log.error("auto provider failed, dropping to operator-only: %s", e)
                request.auto_failed = True
                request.auto_last_error = str(e)
                db.session.commit()
                provider = None
                value = None
            if value:
                fulfill(request, value, source="mailbox")
                return value

        time.sleep(poll_s)

    _close(request, EXPIRED)
    raise InputUnavailable(f"no value for {name!r} within {timeout_s}s")
