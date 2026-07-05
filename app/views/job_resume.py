from flask import flash, redirect, url_for
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRun
from app.models.job_run import RUNNING_STATUSES
from app.services import enqueue_resume


class JobResumeView(MethodView):
    """Resume a finished/failed/stopped run: dispatch a new run that picks up
    where it left off (the launcher seeds it from this run's output dir, so the
    job skips work it already did)."""

    decorators = [login_required]

    def post(self, run_id: int):
        prior = db.get_or_404(JobRun, run_id)
        if prior.job_definition_id is None:
            flash("This run has no job definition, so it can't be resumed.", "error")
            return redirect(url_for("main.run_detail", run_id=run_id))
        if prior.is_running:
            flash("Can't resume a run that's still running.", "warning")
            return redirect(url_for("main.run_detail", run_id=run_id))
        active = db.session.scalar(
            db.select(JobRun)
            .filter_by(job_definition_id=prior.job_definition_id)
            .where(JobRun.status.in_(RUNNING_STATUSES))
            .limit(1)
        )
        if active:
            flash("That job already has a run in progress.", "warning")
            return redirect(url_for("main.run_detail", run_id=run_id))

        batch = enqueue_resume(prior)
        flash("Resuming — continuing from where the previous run left off.", "success")
        return redirect(url_for("main.index", live_run=batch.runs[0].id))
