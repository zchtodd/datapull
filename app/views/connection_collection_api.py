from flask import jsonify, request
from flask.views import MethodView

from app.decorators import admin_required
from app.extensions import db
from app.models import Connection
from app.services import serialize_connection, validate_connection


class ConnectionCollectionAPI(MethodView):
    """Admin JSON API: list and create shared connections."""

    decorators = [admin_required]

    def get(self):
        conns = db.session.scalars(
            db.select(Connection).order_by(Connection.name)
        ).all()
        return jsonify({"connections": [serialize_connection(c) for c in conns]})

    def post(self):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        is_mfa = bool(data.get("is_mfa", False))
        is_shared = bool(data.get("is_shared", False))
        description = (data.get("description") or "").strip()

        error = validate_connection(name)
        if error:
            return jsonify({"error": error}), 400
        if db.session.scalar(db.select(Connection).filter_by(name=name)):
            return jsonify({"error": f"A connection named '{name}' already exists."}), 409

        conn = Connection(name=name, is_mfa=is_mfa, is_shared=is_shared, description=description)
        db.session.add(conn)
        db.session.commit()
        return jsonify(serialize_connection(conn)), 201
