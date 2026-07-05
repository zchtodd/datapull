from datetime import datetime, timezone

from app.extensions import db

# Lifecycle: a script asks for input (PENDING); a provider or an operator
# supplies it (FULFILLED); or it times out (EXPIRED) / the run is cancelled.
PENDING = "PENDING"
FULFILLED = "FULFILLED"
EXPIRED = "EXPIRED"
CANCELLED = "CANCELLED"
OPEN_STATUSES = frozenset({PENDING})


class JobInputRequest(db.Model):
    """A piece of information a running job needs mid-flight (e.g. an MFA code).

    The platform owns delivery: it tries automated providers (e.g. the mailbox
    OTP poller bound via the job's connection) and/or an operator who types the
    value into the UI. The script blocks until this is FULFILLED or EXPIRED.
    """

    __tablename__ = "job_input_requests"

    id = db.Column(db.Integer, primary_key=True)
    job_run_id = db.Column(
        db.Integer, db.ForeignKey("job_runs.id"), nullable=False, index=True
    )
    # Logical name the script asked for (e.g. "okta_mfa") and what kind of value.
    name = db.Column(db.String(128), nullable=False)
    kind = db.Column(db.String(32), nullable=False, default="text")  # text | otp
    prompt = db.Column(db.Text, nullable=False, default="", server_default="")
    status = db.Column(db.String(16), nullable=False, default=PENDING)
    # The supplied answer. Single-use and short-lived; never returned by the API.
    value = db.Column(db.Text, nullable=True)
    # How it was fulfilled: "mailbox" | "operator" | "preset".
    source = db.Column(db.String(32), nullable=True)
    # Automated-retrieval state, used to drive the operator UI: while the
    # platform is still reading the inbox we show a "retrieving automatically"
    # status; the manual entry box only appears once auto-retrieval is no longer
    # an option (disabled, errored, or out of attempts).
    # Was a ready automated provider available when this request opened?
    auto_enabled = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    # How many inbox reads have been attempted for this request.
    auto_attempts = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    # Set once a provider poll raised an error; auto-retrieval stops afterwards.
    auto_failed = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    # Last provider error message (diagnostics; not the supplied value).
    auto_last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    resolved_at = db.Column(db.DateTime, nullable=True)

    job_run = db.relationship("JobRun", back_populates="input_requests")

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def __repr__(self) -> str:
        return f"<JobInputRequest {self.id} name={self.name!r} status={self.status}>"
