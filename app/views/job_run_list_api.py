from flask import jsonify
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRun


class JobRunListView(MethodView):
    """JSON list of job-run history, most recent first (feeds the index grid)."""

    decorators = [login_required]

    def get(self):
        runs = db.session.scalars(
            db.select(JobRun).order_by(JobRun.created_at.desc())
        ).all()
        return jsonify(
            {
                "job_runs": [
                    {
                        "id": r.id,
                        "task_id": r.task_id,
                        "status": r.status,
                        "job_definition": (
                            r.job_definition.name if r.job_definition else None
                        ),
                        "created_at": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                    }
                    for r in runs
                ]
            }
        )
