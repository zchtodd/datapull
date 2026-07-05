from flask import Response, render_template
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRun


class RunDetailView(MethodView):
    """Detail page for a single run — opened from a history cell on the
    dashboard. Shows status, connections used, input requests, and outputs."""

    decorators = [login_required]

    def get(self, run_id: int):
        run = db.get_or_404(JobRun, run_id)
        # Map each failure's evidence filename to its registered output id, so
        # the template can offer a one-click link to the captured screenshot.
        out_by_name = {o.filename: o.id for o in run.outputs}
        evidence_output = {
            f.id: out_by_name.get(f.evidence)
            for f in run.failures if f.evidence
        }
        return render_template(
            "run_detail.html", run=run, evidence_output=evidence_output
        )


class RunStdoutView(MethodView):
    """Download a run's captured stdout as a text file."""

    decorators = [login_required]

    def get(self, run_id: int):
        run = db.get_or_404(JobRun, run_id)
        return Response(
            run.stdout or "",
            mimetype="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="run-{run.id}-stdout.txt"'
            },
        )
