from flask import jsonify, request
from flask.views import MethodView

from app.decorators import admin_required
from app.extensions import db
from app.models import JobDefinition, JobParameter
from app.services import serialize_parameter, validate_parameter


class JobParameterCollectionAPI(MethodView):
    """Admin JSON API: list and create parameters for one job definition."""

    decorators = [admin_required]

    def get(self, definition_id: int):
        definition = db.get_or_404(JobDefinition, definition_id)
        params = sorted(definition.parameters, key=lambda p: p.key.lower())
        return jsonify(
            {
                "job_definition": {"id": definition.id, "name": definition.name},
                "parameters": [serialize_parameter(p) for p in params],
            }
        )

    def post(self, definition_id: int):
        definition = db.get_or_404(JobDefinition, definition_id)
        data = request.get_json(silent=True) or {}
        key = (data.get("key") or "").strip()
        is_secret = bool(data.get("is_secret", False))
        value_type = (data.get("value_type") or "string").strip()
        # Treat blank as "no value"; the column is nullable.
        value = data.get("value") or None

        error = validate_parameter(key, value_type, value)
        if error:
            return jsonify({"error": error}), 400
        if any(p.key == key for p in definition.parameters):
            return jsonify({"error": f"A parameter named '{key}' already exists."}), 409

        # Set is_secret before value so the value setter encrypts when needed.
        param = JobParameter(
            job_definition_id=definition.id,
            key=key,
            is_secret=is_secret,
            value_type=value_type,
        )
        param.value = value
        db.session.add(param)
        db.session.commit()
        return jsonify(serialize_parameter(param)), 201
