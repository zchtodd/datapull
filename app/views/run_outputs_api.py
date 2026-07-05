from flask import jsonify, url_for
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRun
from app.runtime.failures import serialize_failure
from app.runtime.progress import serialize_progress


class RunOutputsAPI(MethodView):
    """Live outputs for a run so the run-detail page can show downloads as they
    arrive — the launcher registers them incrementally while the run executes.
    Also reports the run status so the poller knows when to stop."""

    decorators = [login_required]

    def get(self, run_id: int):
        run = db.get_or_404(JobRun, run_id)

        def ser(o):
            return {
                "id": o.id,
                "filename": o.filename,
                "size_bytes": o.size_bytes,
                "is_new": o.is_new,
                "url": url_for("main.output_download", output_id=o.id),
            }

        # Link each failure's evidence filename to its registered output, if any.
        out_by_name = {o.filename: o.id for o in run.outputs}

        def ser_fail(f):
            oid = out_by_name.get(f.evidence) if f.evidence else None
            url = url_for("main.output_download", output_id=oid) if oid else None
            return serialize_failure(f, evidence_url=url)

        return jsonify({
            "status": run.status,
            "is_running": run.is_running,
            "downloads": [ser(o) for o in run.outputs if not o.is_system],
            "system_count": sum(1 for o in run.outputs if o.is_system),
            "failures": [ser_fail(f) for f in run.failures],
            "failed_count": len(run.failures),
            "zip_url": url_for("main.run_downloads_zip", run_id=run.id),
            "progress": serialize_progress(run),
        })
