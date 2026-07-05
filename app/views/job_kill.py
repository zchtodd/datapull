from flask import current_app, flash, redirect, url_for
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobDefinition, JobRun
from app.models.job_run import RUNNING_STATUSES


class JobKillView(MethodView):
    """Stop the currently-running run of a job definition."""

    decorators = [login_required]

    def post(self, definition_id: int):
        definition = db.get_or_404(JobDefinition, definition_id)

        # Stop every active child of this job (a fan-out batch has several).
        runs = db.session.scalars(
            db.select(JobRun)
            .filter_by(job_definition_id=definition.id)
            .where(JobRun.status.in_(RUNNING_STATUSES))
        ).all()
        if not runs:
            flash(f"{definition.name} is not running.", "warning")
            return redirect(url_for("main.index"))

        from app.runtime.launcher import register_outputs, stop_job
        celery = current_app.extensions["celery"]
        for run in runs:
            # Stop the container (the actual work), then terminate the worker
            # task. A terminated worker can't update its JobRun, so mark it here.
            try:
                stop_job(run.id)
            except Exception:
                current_app.logger.exception("stop_job failed for run %s", run.id)
            celery.control.revoke(run.task_id, terminate=True, signal="SIGTERM")
            # The terminated worker never reaches its register_outputs() call, so
            # register whatever the job already downloaded to the shared volume
            # here — otherwise a stopped run shows no outputs despite having some.
            try:
                register_outputs(run.id)
            except Exception:
                current_app.logger.exception("register_outputs failed for run %s", run.id)
            run.status = "STOPPED"
        db.session.commit()
        flash(f"Stopped {definition.name}.", "success")
        return redirect(url_for("main.index"))
