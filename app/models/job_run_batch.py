from datetime import datetime, timezone

from app.extensions import db
from app.models.job_run import RUNNING_STATUSES


class JobRunBatch(db.Model):
    """One execution of a job definition. Holds one child JobRun per client
    (fan-out), or a single child for a non-fan-out job. The dashboard history
    strip shows batches; the rollup summarizes the children."""

    __tablename__ = "job_run_batches"

    id = db.Column(db.Integer, primary_key=True)
    job_definition_id = db.Column(
        db.Integer, db.ForeignKey("job_definitions.id"), nullable=True, index=True
    )
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    job_definition = db.relationship("JobDefinition")
    runs = db.relationship(
        "JobRun", back_populates="batch", order_by="JobRun.id"
    )

    @property
    def counts(self) -> dict:
        c = {"total": 0, "success": 0, "failed": 0, "running": 0}
        for r in self.runs:
            c["total"] += 1
            if r.status in RUNNING_STATUSES:
                c["running"] += 1
            elif r.status == "SUCCESS":
                c["success"] += 1
            else:  # FAILURE / STOPPED / etc.
                c["failed"] += 1
        return c

    @property
    def rollup_status(self) -> str:
        """SUCCESS (all ok), FAILURE (none ok), PARTIAL (mixed), RUNNING, or
        PENDING (no children yet)."""
        c = self.counts
        if c["total"] == 0:
            return "PENDING"
        if c["running"]:
            return "RUNNING"
        if c["success"] == c["total"]:
            return "SUCCESS"
        if c["success"] == 0:
            return "FAILURE"
        return "PARTIAL"

    @property
    def is_running(self) -> bool:
        return any(r.status in RUNNING_STATUSES for r in self.runs)

    @property
    def failed_item_count(self) -> int:
        """Total individual items (e.g. invoices) that failed across the batch's
        runs — distinct from counts['failed'], which counts failed runs."""
        return sum(len(r.failures) for r in self.runs)

    def __repr__(self) -> str:
        return f"<JobRunBatch {self.id} def={self.job_definition_id} runs={len(self.runs)}>"
