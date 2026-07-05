"""Job-reported failures: a running job records units of work it couldn't
complete (e.g. an invoice that wouldn't download) through the runtime API, so
they're surfaced to operators as first-class data rather than buried in a log
or the audit CSV. The job side calls the SDK's report_failure()."""
from app.extensions import db
from app.models import JobRunFailure


def record_failure(job_run_id, item, kind="", label=None, detail=None,
                   evidence=None) -> JobRunFailure:
    f = JobRunFailure(
        job_run_id=job_run_id, item=item, kind=kind or "",
        label=label or None, detail=detail or None, evidence=evidence or None,
    )
    db.session.add(f)
    db.session.commit()
    return f


def serialize_failure(f: JobRunFailure, evidence_url=None) -> dict:
    return {
        "id": f.id,
        "item": f.item,
        "kind": f.kind,
        "label": f.label,
        "detail": f.detail,
        "evidence_url": evidence_url,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
