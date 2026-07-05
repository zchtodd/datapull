"""Generic per-run progress. The job declares its total work and reports
completed units through the runtime API; meaning is job-defined."""
from datetime import datetime, timezone

from app.extensions import db


def update_progress(run, total=None, current=None, advance=None, message=None):
    """Apply a progress update to a JobRun and commit. Any subset of fields may
    be given: `total` sets the denominator, `current` sets the absolute count,
    `advance` increments it, `message` sets the human label."""
    changed = False
    if total is not None:
        run.progress_total = max(0, int(total))
        changed = True
    if current is not None:
        run.progress_current = max(0, int(current))
        changed = True
    if advance is not None:
        run.progress_current = max(0, (run.progress_current or 0) + int(advance))
        changed = True
    if message is not None:
        run.progress_message = str(message)[:255]
        changed = True
    if changed:
        run.progress_updated_at = datetime.now(timezone.utc)
        db.session.commit()
    return run


def serialize_progress(run) -> dict:
    return {
        "total": run.progress_total,
        "current": run.progress_current or 0,
        "percent": run.progress_percent,
        "message": run.progress_message,
        "updated_at": run.progress_updated_at.isoformat() if run.progress_updated_at else None,
    }
