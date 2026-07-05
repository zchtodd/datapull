"""Key-based completion checkpoints so jobs can skip work they've already done,
across runs (including resumes). Scoped to (job_definition, namespace, key);
the job decides what a key/namespace mean."""
from datetime import datetime, timezone

from app.extensions import db
from app.models import JobCheckpoint
from app.models.job_checkpoint import DONE


def mark_checkpoint(definition_id, namespace, key, status=DONE) -> JobCheckpoint:
    """Upsert a checkpoint. Single-writer per definition (start/resume guard on
    it), so the read-then-write here stays one row per key."""
    cp = db.session.scalar(
        db.select(JobCheckpoint).filter_by(
            job_definition_id=definition_id, namespace=namespace, key=key)
    )
    now = datetime.now(timezone.utc)
    if cp is None:
        cp = JobCheckpoint(
            job_definition_id=definition_id, namespace=namespace, key=key,
            status=status, created_at=now, updated_at=now,
        )
        db.session.add(cp)
    else:
        cp.status = status
        cp.updated_at = now
    db.session.commit()
    return cp


def checkpoint_status(definition_id, namespace, key):
    """The status of one key, or None if it has never been recorded."""
    cp = db.session.scalar(
        db.select(JobCheckpoint).filter_by(
            job_definition_id=definition_id, namespace=namespace, key=key)
    )
    return cp.status if cp else None


def done_keys(definition_id, namespace, status=DONE) -> list:
    """All keys at the given status in this namespace (the skip set)."""
    return list(db.session.scalars(
        db.select(JobCheckpoint.key).filter_by(
            job_definition_id=definition_id, namespace=namespace, status=status)
    ).all())
