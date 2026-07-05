from datetime import datetime, timezone

from app.extensions import db


class JobRunFailure(db.Model):
    """A single unit of work a job could not complete (e.g. an invoice that
    failed to download). Reported by the running job through the runtime API so
    failures are first-class, queryable data — not buried in a log or CSV.

    Job-agnostic: `item` identifies the thing that failed, `kind` is an optional
    subtype the job defines (Prime uses the report type — PDF/CMS), `label` is
    human context (Prime uses "<business line> / <program>"), `detail` is the
    error, and `evidence` is the filename of a captured screenshot/artifact
    (matched to a JobRunOutput to offer a download link).
    """

    __tablename__ = "job_run_failures"

    id = db.Column(db.Integer, primary_key=True)
    job_run_id = db.Column(
        db.Integer, db.ForeignKey("job_runs.id"), nullable=False, index=True
    )
    item = db.Column(db.String(512), nullable=False)
    kind = db.Column(db.String(64), nullable=False, default="", server_default="")
    label = db.Column(db.String(512), nullable=True)
    detail = db.Column(db.Text, nullable=True)
    evidence = db.Column(db.String(1024), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    job_run = db.relationship("JobRun", back_populates="failures")

    def __repr__(self) -> str:
        return f"<JobRunFailure {self.id} item={self.item!r} kind={self.kind!r}>"
