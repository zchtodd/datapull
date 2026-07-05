from datetime import datetime, timezone

from app.extensions import db

DONE = "DONE"


class JobCheckpoint(db.Model):
    """A generic, key-based completion marker so a job can skip work it has
    already finished — across runs, including resumes.

    Scoped to (job_definition, namespace, key): the job picks what a "key" means
    (a unit of work) and groups keys under a "namespace" so unrelated batches of
    work don't collide (Prime uses the quarter as the namespace and
    "<business line>||<program>" as the key). A job marks a key DONE when it
    finishes that unit, and checks keys at startup to skip already-done ones.

    No DB-level unique constraint: MSSQL caps index keys at 900 bytes and `key`
    can be long, and only one run of a definition executes at a time (start/
    resume both guard on that), so the app-level upsert in runtime/checkpoints.py
    keeps it single-row per key. Any rare duplicate is harmless (the reader
    de-dupes).
    """

    __tablename__ = "job_checkpoints"

    id = db.Column(db.Integer, primary_key=True)
    job_definition_id = db.Column(
        db.Integer, db.ForeignKey("job_definitions.id"), nullable=False
    )
    namespace = db.Column(db.String(128), nullable=False, default="", server_default="")
    key = db.Column(db.String(512), nullable=False)
    status = db.Column(db.String(32), nullable=False, default=DONE, server_default=DONE)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        db.Index("ix_job_checkpoints_def_ns", "job_definition_id", "namespace"),
    )

    def __repr__(self) -> str:
        return (f"<JobCheckpoint def={self.job_definition_id} "
                f"ns={self.namespace!r} key={self.key!r} status={self.status}>")
