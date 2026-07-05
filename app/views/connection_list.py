from flask import render_template
from flask.views import MethodView

from app.decorators import admin_required


class ConnectionListView(MethodView):
    """Admin-only page for managing shared connections."""

    decorators = [admin_required]

    def get(self):
        return render_template("admin/connections.html")
