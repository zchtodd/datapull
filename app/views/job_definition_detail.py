from flask import render_template
from flask.views import MethodView

from app.decorators import admin_required
from app.extensions import db
from app.models import JobDefinition


class JobDefinitionDetailView(MethodView):
    """Admin-only detail view for a single job definition."""

    decorators = [admin_required]

    def get(self, definition_id: int):
        definition = db.get_or_404(JobDefinition, definition_id)
        return render_template(
            "admin/job_definition_detail.html", definition=definition
        )
