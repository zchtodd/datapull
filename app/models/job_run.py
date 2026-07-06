from datetime import datetime, timezone

from app.extensions import db

# Statuses that mean the run is dispatched but not yet finished.
RUNNING_STATUSES = frozenset({"PENDING", "STARTED", "PROGRESS", "RUNNING"})


class JobRun(db.Model):
    """A record of what *did* happen: one execution dispatched to Celery.

    Optionally linked to the JobDefinition it was run from (null for ad-hoc runs).
    """

    __tablename__ = "job_runs"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(64), unique=True, index=True, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="PENDING")
    job_definition_id = db.Column(
        db.Integer, db.ForeignKey("job_definitions.id"), nullable=True, index=True
    )
    # The execution (batch) this run belongs to, and which client it ran for
    # (the client connection's name) for fan-out jobs.
    batch_id = db.Column(
        db.Integer, db.ForeignKey("job_run_batches.id"), nullable=True, index=True
    )
    client_label = db.Column(db.String(255), nullable=True)
    # If set, this run is a resume of an earlier run: the launcher seeds this
    # run's output dir from that run's files (and pins its quarter) so the job
    # skips already-completed work instead of redoing it from scratch.
    resume_from_run_id = db.Column(
        db.Integer, db.ForeignKey("job_runs.id"), nullable=True, index=True
    )
    # Force a clean run: ignore checkpoints (don't skip completed work) and skip
    # prior-file seeding, so everything is re-scraped/re-downloaded. Opt-in per
    # run from the Run dialog; uncommon.
    from_scratch = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    # The job's process exit code (null until it finishes). Used to decide
    # whether a failure is worth auto-resuming (transient) or not (config/403).
    exit_code = db.Column(db.Integer, nullable=True)
    # How many times this run's chain has been auto-resumed (0 = an original run
    # or a manual resume, which resets the budget). Capped per definition.
    auto_resume_attempt = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    # When the server intends to auto-resume this (failed) run. Drives the UI
    # countdown; cleared once the resume is created or superseded by a manual one.
    auto_resume_at = db.Column(db.DateTime, nullable=True)
    # SHA-256 of the per-run bearer token the running job uses to call the
    # runtime API (request inputs scoped to this run). Null until issued.
    runtime_token_hash = db.Column(db.String(64), nullable=True, index=True)
    # Captured container stdout/stderr, written when the run finishes.
    stdout = db.Column(db.Text, nullable=True)
    # Generic progress tracking. The job declares how much total work there is
    # (progress_total) and reports completed units (progress_current) via the
    # runtime API; the meaning of a "unit" is job-defined. progress_message is an
    # optional human label (e.g. the item currently being worked).
    progress_total = db.Column(db.Integer, nullable=True)
    progress_current = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    progress_message = db.Column(db.String(255), nullable=True)
    progress_updated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    job_definition = db.relationship("JobDefinition", back_populates="runs")
    outputs = db.relationship(
        "JobRunOutput", back_populates="job_run",
        order_by="JobRunOutput.filename", cascade="all, delete-orphan"
    )
    input_requests = db.relationship(
        "JobInputRequest", back_populates="job_run", cascade="all, delete-orphan"
    )
    failures = db.relationship(
        "JobRunFailure", back_populates="job_run",
        order_by="JobRunFailure.id", cascade="all, delete-orphan"
    )
    connections = db.relationship(
        "JobRunConnection", back_populates="job_run", cascade="all, delete-orphan"
    )
    batch = db.relationship("JobRunBatch", back_populates="runs")
    # The earlier run this one resumes from (many-to-one self reference).
    resume_from = db.relationship("JobRun", remote_side=[id])

    @property
    def is_running(self) -> bool:
        return self.status in RUNNING_STATUSES

    @property
    def progress_percent(self):
        """Completed percentage (0-100), or None if the total isn't known."""
        if self.progress_total and self.progress_total > 0:
            return min(100, round((self.progress_current or 0) / self.progress_total * 100))
        return None

    def __repr__(self) -> str:
        return f"<JobRun {self.id} task_id={self.task_id} status={self.status}>"
