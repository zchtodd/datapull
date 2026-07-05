from flask import redirect, render_template, url_for
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRunBatch


class BatchDetailView(MethodView):
    """An execution: rollup + per-client child runs. Opened from a history cell."""

    decorators = [login_required]

    def get(self, batch_id: int):
        batch = db.get_or_404(JobRunBatch, batch_id)
        # A non-fan-out batch has a single child run; the batch rollup adds
        # nothing, so send the user straight to that run's detail page.
        if len(batch.runs) == 1:
            return redirect(url_for("main.run_detail", run_id=batch.runs[0].id))
        download_count = sum(
            1 for r in batch.runs for o in r.outputs if not o.is_system
        )
        return render_template("batch_detail.html", batch=batch,
                               download_count=download_count)
