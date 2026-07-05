from flask import jsonify, request
from flask.views import MethodView

from app.decorators import admin_required
from app.extensions import db
from app.models import ConnectionParameter
from app.services import serialize_parameter, validate_parameter


class ConnectionParameterItemAPI(MethodView):
    """Admin JSON API: update and delete a single connection parameter."""

    decorators = [admin_required]

    def patch(self, parameter_id: int):
        param = db.get_or_404(ConnectionParameter, parameter_id)
        data = request.get_json(silent=True) or {}

        new_key = (data.get("key", param.key) or "").strip()
        new_is_secret = bool(data.get("is_secret", param.is_secret))
        new_value_type = (data.get("value_type", param.value_type) or "string").strip()

        # Blank/omitted value keeps the current one; toggling is_secret re-encodes
        # (decode under the current flag, re-store under the new one).
        value_provided = "value" in data and data.get("value") not in (None, "")
        secret_changed = new_is_secret != param.is_secret
        if value_provided:
            plaintext = data["value"]
        elif secret_changed:
            plaintext = param.value
        else:
            plaintext = None

        if value_provided or secret_changed:
            check_value = plaintext
        else:
            check_value = None if param.is_secret else param.value
        error = validate_parameter(new_key, new_value_type, check_value)
        if error:
            return jsonify({"error": error}), 400

        if new_key != param.key:
            clash = db.session.scalar(
                db.select(ConnectionParameter).where(
                    ConnectionParameter.connection_id == param.connection_id,
                    ConnectionParameter.key == new_key,
                    ConnectionParameter.id != param.id,
                )
            )
            if clash:
                return jsonify({"error": f"A parameter named '{new_key}' already exists."}), 409

        param.key = new_key
        param.value_type = new_value_type
        if value_provided or secret_changed:
            param.is_secret = new_is_secret
            param.value = plaintext

        db.session.commit()
        return jsonify(serialize_parameter(param))

    def delete(self, parameter_id: int):
        param = db.get_or_404(ConnectionParameter, parameter_id)
        db.session.delete(param)
        db.session.commit()
        return "", 204
