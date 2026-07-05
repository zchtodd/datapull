"""Per-run bearer tokens: how a job's subprocess authenticates to the runtime
API. The token is issued when the run is dispatched and handed to the subprocess
via an environment variable; only the SHA-256 is stored, and it scopes API
access to that one JobRun.
"""
import hashlib
import secrets
from functools import wraps

from flask import g, jsonify, request

from app.extensions import db
from app.models import JobRun


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_run_token(job_run: JobRun) -> str:
    """Generate a token for this run, store its hash, return the plaintext.
    Caller is responsible for committing."""
    token = secrets.token_urlsafe(32)
    job_run.runtime_token_hash = _hash(token)
    return token


def run_from_token(token: str | None) -> JobRun | None:
    if not token:
        return None
    return db.session.scalar(
        db.select(JobRun).filter_by(runtime_token_hash=_hash(token))
    )


def _extract_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return request.headers.get("X-Datapull-Run-Token", "").strip() or None


def run_token_required(view):
    """Authenticate a runtime API call by its per-run token, exposing the
    resolved JobRun as flask.g.runtime_run."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        run = run_from_token(_extract_token())
        if run is None:
            return jsonify({"error": "Invalid or missing run token."}), 401
        g.runtime_run = run
        return view(*args, **kwargs)

    return wrapped
