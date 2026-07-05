from flask import render_template
from flask.views import MethodView

from app.decorators import admin_required


class JobDefinitionListView(MethodView):
    """Admin-only management page; rows are loaded client-side via the JSON API."""

    decorators = [admin_required]

    def get(self):
        return render_template("admin/job_definitions.html")
