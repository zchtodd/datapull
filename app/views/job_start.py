from flask import flash, redirect, request, url_for
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobDefinition, JobRun
from app.models.job_run import RUNNING_STATUSES
from app.services import enqueue_batch, resolve_connection_ids


class JobStartView(MethodView):
    """Manually start a job definition (creates a JobRun and dispatches it)."""

    decorators = [login_required]

    def post(self, definition_id: int):
        definition = db.get_or_404(JobDefinition, definition_id)

        already_running = db.session.scalar(
            db.select(JobRun)
            .filter_by(job_definition_id=definition.id)
            .where(JobRun.status.in_(RUNNING_STATUSES))
            .limit(1)
        )
        if already_running:
            flash(f"{definition.name} is already running.", "warning")
            return redirect(url_for("main.index"))

        # Attached connections: definition defaults, unless the Run dialog
        # submitted an explicit choice (marked by `override`).
        if request.form.get("override"):
            raw_ids = request.form.getlist("connection_ids")
            cids, err = resolve_connection_ids(raw_ids)
            if err:
                flash(err, "error")
                return redirect(url_for("main.index"))
        else:
            cids = [b.connection_id for b in definition.connection_bindings]

        batch = enqueue_batch(definition, connection_ids=cids)
        flash(f"Started {definition.name}.", "success")
        # One client -> auto-open its live view; several -> show the batch page.
        if len(batch.runs) == 1:
            return redirect(url_for("main.index", live_run=batch.runs[0].id))
        return redirect(url_for("main.batch_detail", batch_id=batch.id))
