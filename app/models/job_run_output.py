from datetime import datetime, timezone

from app.extensions import db

# A run's output dir mixes the files the user actually wants (downloads, which
# the job nests under per-result subfolders) with diagnostic artifacts written
# at the run-dir root: the audit manifest, the debug run.log, and failure
# screenshots/HTML (dump_failure prefixes every one with "fail_"). Classify by
# these well-known system artifacts; everything else is a user-facing download.
_SYSTEM_NAMES = frozenset({"run.log", "manifest.csv", "manifest.json"})
_SYSTEM_PREFIXES = ("fail_",)
_SYSTEM_EXTS = (".log",)


class JobRunOutput(db.Model):
    """A downloadable file produced by a JobRun.

    The file itself lives under the configured OUTPUTS_DIR; `storage_path` is
    its location relative to that directory. `filename` is the name presented
    to the user on download.
    """

    __tablename__ = "job_run_outputs"

    id = db.Column(db.Integer, primary_key=True)
    job_run_id = db.Column(
        db.Integer, db.ForeignKey("job_runs.id"), nullable=False, index=True
    )
    filename = db.Column(db.String(512), nullable=False)
    storage_path = db.Column(db.String(1024), nullable=False)
    content_type = db.Column(db.String(255), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=True)
    # SHA-256 of the file's content, and whether that content was new at the
    # time this run registered it (i.e. no earlier run of the same job had
    # already produced an identical file). Both null until computed.
    content_hash = db.Column(db.String(64), nullable=True, index=True)
    is_new = db.Column(db.Boolean, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    job_run = db.relationship("JobRun", back_populates="outputs")

    @property
    def is_system(self) -> bool:
        """True for diagnostic/system artifacts (the audit manifest, debug
        run.log, failure screenshots/HTML); False for the actual downloaded
        deliverables the user is after."""
        name = self.filename.lower()
        return (name in _SYSTEM_NAMES
                or name.startswith(_SYSTEM_PREFIXES)
                or name.endswith(_SYSTEM_EXTS))

    @property
    def category(self) -> str:
        return "system" if self.is_system else "download"

    def __repr__(self) -> str:
        return f"<JobRunOutput {self.id} filename={self.filename!r}>"
