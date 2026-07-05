"""datapull runtime SDK — drop-in client a job script uses to obtain inputs
(MFA codes, prompts, approvals) from the platform at runtime.

Stdlib only, so it vendors into any Python job with no dependencies. The job is
launched with two environment variables:

    DATAPULL_API_BASE   e.g. http://web:5000/api
    DATAPULL_RUN_TOKEN  the per-run bearer token

Usage inside a job:

    from datapull_runtime import request_input
    code = request_input("okta_mfa", kind="otp",
                         prompt="Enter the Okta email verification code")

The call blocks (polling the platform) until the platform resolves the request
— either automatically (e.g. the mailbox OTP provider) or via an operator who
types it into the UI — or raises InputTimeout.
"""
import json
import os
import time
import urllib.error
import urllib.request

# Job process exit codes — the contract between a job and the platform that
# launches it. The platform reads these to decide success vs failure and whether
# a failure is worth auto-resuming. Jobs should exit with one of these rather
# than bare integers, and the platform should compare against these names.
EXIT_OK = 0           # completed successfully
EXIT_UNEXPECTED = 1   # unhandled/unknown error (often transient)
EXIT_CONFIG = 2       # bad or missing configuration (not retryable)
EXIT_LOGIN = 3        # login failed (sometimes transient, e.g. cert/cookies)
EXIT_MFA = 4          # MFA not supplied in time / session expired (transient)
EXIT_FORBIDDEN = 5    # portal denied access / 403 (not retryable)


class RuntimeError_(Exception):
    """Misconfiguration or transport error talking to the platform."""


class InputTimeout(Exception):
    """The requested input was not supplied before the timeout."""


class RuntimeClient:
    def __init__(self, base=None, token=None):
        self.base = (base or os.environ.get("DATAPULL_API_BASE", "")).rstrip("/")
        self.token = token or os.environ.get("DATAPULL_RUN_TOKEN", "")
        if not self.base or not self.token:
            raise RuntimeError_(
                "DATAPULL_API_BASE and DATAPULL_RUN_TOKEN must be set "
                "(the platform sets these when it launches the job)."
            )

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise RuntimeError_(f"runtime API {method} {path} -> HTTP {e.code}: {detail}") from e

    def update_progress(self, total=None, current=None, advance=None, message=None):
        """Report progress to the platform. `total` sets how much work there is,
        `current`/`advance` set/increment completed units, `message` is a label.
        Returns the platform's current progress state."""
        body = {}
        if total is not None:
            body["total"] = total
        if current is not None:
            body["current"] = current
        if advance is not None:
            body["advance"] = advance
        if message is not None:
            body["message"] = message
        return self._call("POST", "/runtime/progress", body)

    def mark_checkpoint(self, key, namespace="", status="DONE"):
        """Record that a unit of work (`key`, grouped under `namespace`) is done,
        so future runs can skip it."""
        return self._call("POST", "/runtime/checkpoints",
                          {"key": key, "namespace": namespace, "status": status})

    def get_checkpoints(self, namespace="", key=None):
        """Without `key`: the set of done keys in `namespace`. With `key`: that
        key's status."""
        from urllib.parse import urlencode
        q = {"namespace": namespace}
        if key is not None:
            q["key"] = key
        return self._call("GET", "/runtime/checkpoints?" + urlencode(q))

    def request_input(self, name, kind="text", prompt="", timeout=300, poll=4):
        """Open an input request and block until it's fulfilled. Returns the
        value, or raises InputTimeout / RuntimeError_."""
        created = self._call("POST", "/runtime/inputs",
                             {"name": name, "kind": kind, "prompt": prompt})
        rid = created["id"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            cur = self._call("GET", f"/runtime/inputs/{rid}")
            status = cur.get("status")
            if status == "FULFILLED" and cur.get("value"):
                return cur["value"]
            if status in ("EXPIRED", "CANCELLED"):
                raise InputTimeout(f"input {name!r} was {status.lower()}")
            time.sleep(poll)
        raise InputTimeout(f"no value for {name!r} within {timeout}s")

    def report_failure(self, item, kind="", label="", detail="", evidence=""):
        """Record a unit of work the job couldn't complete (e.g. a file that
        failed to download), so the platform can surface it to operators."""
        return self._call("POST", "/runtime/failures", {
            "item": str(item), "kind": kind, "label": label,
            "detail": detail, "evidence": evidence,
        })


def request_input(name, **kwargs):
    """Convenience wrapper using DATAPULL_API_BASE / DATAPULL_RUN_TOKEN."""
    return RuntimeClient().request_input(name, **kwargs)


# Progress reporting is non-critical: never let a failed update crash the job.
def _safe_progress(**kwargs):
    try:
        return RuntimeClient().update_progress(**kwargs)
    except Exception:
        return None


def set_progress_total(total, message=None):
    """Declare how much total work there is, before starting."""
    return _safe_progress(total=total, message=message)


def advance_progress(n=1, message=None):
    """Mark n more units of work done."""
    return _safe_progress(advance=n, message=message)


def set_progress(current, total=None, message=None):
    """Set the absolute completed count (and optionally the total)."""
    return _safe_progress(current=current, total=total, message=message)


# Checkpoints: best-effort key-based completion tracking for skip/resume.
def checkpoint_done(key, namespace="", status="DONE"):
    """Mark a unit of work done so future runs skip it."""
    try:
        return RuntimeClient().mark_checkpoint(key, namespace, status)
    except Exception:
        return None


def checkpoint_status(key, namespace=""):
    """The recorded status of `key`, or None if never recorded / on error."""
    try:
        return (RuntimeClient().get_checkpoints(namespace, key) or {}).get("status")
    except Exception:
        return None


def completed_checkpoints(namespace=""):
    """The set (list) of done keys in `namespace`; [] on error."""
    try:
        return (RuntimeClient().get_checkpoints(namespace) or {}).get("keys", [])
    except Exception:
        return []


# Failure reporting: best-effort, so reporting a failure can never fail the job.
def report_failure(item, kind="", label="", detail="", evidence=""):
    """Record a unit of work the job couldn't complete (e.g. an invoice that
    failed to download). `item` identifies it, `kind` is an optional subtype,
    `label` is human context, `detail` is the error, and `evidence` is the
    filename of a captured screenshot/artifact for this run."""
    try:
        return RuntimeClient().report_failure(item, kind, label, detail, evidence)
    except Exception:
        return None
