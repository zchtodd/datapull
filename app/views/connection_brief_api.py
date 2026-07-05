from flask import jsonify
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import Connection


class ConnectionBriefListAPI(MethodView):
    """Minimal connection list (id/name/type, never secrets) for any logged-in
    user — feeds the Run dialog's per-role connection pickers."""

    decorators = [login_required]

    def get(self):
        conns = db.session.scalars(
            db.select(Connection).order_by(Connection.name)
        ).all()
        return jsonify({
            "connections": [
                {"id": c.id, "name": c.name, "is_mfa": c.is_mfa, "is_shared": c.is_shared}
                for c in conns
            ]
        })
