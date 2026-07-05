from flask import jsonify, request
from flask.views import MethodView

from app.decorators import admin_required
from app.extensions import db
from app.models import Connection, ConnectionParameter
from app.services import serialize_parameter, validate_parameter


class ConnectionParameterCollectionAPI(MethodView):
    """Admin JSON API: list and create parameters for one connection."""

    decorators = [admin_required]

    def get(self, connection_id: int):
        conn = db.get_or_404(Connection, connection_id)
        params = sorted(conn.parameters, key=lambda p: p.key.lower())
        return jsonify(
            {
                "connection": {"id": conn.id, "name": conn.name, "is_mfa": conn.is_mfa},
                "parameters": [serialize_parameter(p) for p in params],
            }
        )

    def post(self, connection_id: int):
        conn = db.get_or_404(Connection, connection_id)
        data = request.get_json(silent=True) or {}
        key = (data.get("key") or "").strip()
        is_secret = bool(data.get("is_secret", False))
        value_type = (data.get("value_type") or "string").strip()
        value = data.get("value") or None

        error = validate_parameter(key, value_type, value)
        if error:
            return jsonify({"error": error}), 400
        if any(p.key == key for p in conn.parameters):
            return jsonify({"error": f"A parameter named '{key}' already exists."}), 409

        # Set is_secret before value so the value setter encrypts when needed.
        param = ConnectionParameter(
            connection_id=conn.id,
            key=key,
            is_secret=is_secret,
            value_type=value_type,
        )
        param.value = value
        db.session.add(param)
        db.session.commit()
        return jsonify(serialize_parameter(param)), 201
