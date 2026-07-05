from datetime import datetime, timezone

from app.extensions import db
from app.scheduling import next_run_at


class JobDefinition(db.Model):
    """How to run something: a named Node/Puppeteer script and its schedule."""

    __tablename__ = "job_definitions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, index=True, nullable=False)
    # One to two paragraphs describing what this job does.
    description = db.Column(db.Text, nullable=False, default="", server_default="")
    # Filesystem location of the Node script to execute.
    script_path = db.Column(db.String(1024), nullable=False)
    # Cron-like expression controlling when it runs; null means manual-only.
    schedule = db.Column(db.String(255), nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # Auto-resume: when enabled, a failed run with a retryable exit code is
    # automatically resumed (up to auto_resume_max_attempts times) without an
    # operator. Opt-in per job; the cap is the natural limit on retries.
    auto_resume_enabled = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
    )
    auto_resume_max_attempts = db.Column(
        db.Integer, nullable=False, default=3, server_default="3"
    )
    # The most recent cron fire-time the scheduler has already acted on (naive
    # UTC). Lets the tick enqueue each slot exactly once and avoids firing for
    # slots that elapsed before the schedule was set.
    last_scheduled_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Default connection-per-role bindings (e.g. mfa -> a graph_mailbox conn,
    # account -> a prime_account conn). Overridable at launch.
    connection_bindings = db.relationship(
        "JobDefinitionConnection",
        back_populates="job_definition",
        cascade="all, delete-orphan",
    )

    parameters = db.relationship(
        "JobParameter",
        back_populates="job_definition",
        cascade="all, delete-orphan",
    )
    runs = db.relationship("JobRun", back_populates="job_definition")

    @property
    def next_run(self) -> datetime | None:
        """When this job will next fire, or None if disabled/unscheduled."""
        if not self.is_enabled:
            return None
        return next_run_at(self.schedule)

    def __repr__(self) -> str:
        return f"<JobDefinition {self.id} name={self.name!r}>"
