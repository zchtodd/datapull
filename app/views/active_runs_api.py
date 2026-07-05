from flask import jsonify
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRun
from app.models.job_run import RUNNING_STATUSES


class ActiveRunsAPI(MethodView):
    """Map of job_definition_id -> currently-running run id. The dashboard polls
    this and reloads when it diverges from what was rendered, so cards flip to
    Stop + Live view (and back) without a manual refresh."""

    decorators = [login_required]

    def get(self):
        runs = db.session.scalars(
            db.select(JobRun)
            .where(JobRun.status.in_(RUNNING_STATUSES),
                   JobRun.job_definition_id.isnot(None))
            .order_by(JobRun.id)
        ).all()
        # Map def -> running batch id (children share a batch), so the value is
        # stable regardless of which child the dashboard rendered.
        active = {str(r.job_definition_id): (r.batch_id or r.id) for r in runs}
        return jsonify({"active": active})
