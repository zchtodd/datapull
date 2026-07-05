from flask import jsonify, request
from flask.views import MethodView

from app.decorators import admin_required
from app.extensions import db
from app.models import JobDefinition
from app.services import (
    apply_definition_connections,
    clamp_auto_resume_attempts,
    serialize_job_definition,
    validate_job_definition,
)


class JobDefinitionItemAPI(MethodView):
    """Admin JSON API: update and delete a single job definition."""

    decorators = [admin_required]

    def patch(self, definition_id: int):
        definition = db.get_or_404(JobDefinition, definition_id)
        data = request.get_json(silent=True) or {}

        name = (data.get("name", definition.name) or "").strip()
        script_path = (data.get("script_path", definition.script_path) or "").strip()
        description = (data.get("description", definition.description) or "").strip()
        schedule = data.get("schedule", definition.schedule)
        schedule = (schedule or "").strip() or None
        is_enabled = bool(data.get("is_enabled", definition.is_enabled))
        auto_resume_enabled = bool(
            data.get("auto_resume_enabled", definition.auto_resume_enabled))
        auto_resume_max_attempts = clamp_auto_resume_attempts(
            data.get("auto_resume_max_attempts", definition.auto_resume_max_attempts),
            default=definition.auto_resume_max_attempts)

        error = validate_job_definition(name, script_path, description, schedule)
        if error:
            return jsonify({"error": error}), 400
        clash = db.session.scalar(
            db.select(JobDefinition).where(
                JobDefinition.name == name, JobDefinition.id != definition.id
            )
        )
        if clash:
            return jsonify({"error": f"A job named '{name}' already exists."}), 409

        if "connection_ids" in data:
            bind_err = apply_definition_connections(definition, data.get("connection_ids"))
            if bind_err:
                return jsonify({"error": bind_err}), 400

        definition.name = name
        definition.script_path = script_path
        definition.description = description
        definition.schedule = schedule
        definition.is_enabled = is_enabled
        definition.auto_resume_enabled = auto_resume_enabled
        definition.auto_resume_max_attempts = auto_resume_max_attempts
        db.session.commit()
        return jsonify(serialize_job_definition(definition))

    def delete(self, definition_id: int):
        definition = db.get_or_404(JobDefinition, definition_id)
        # Preserve run history: unlink runs so the FK doesn't block the delete.
        # Parameters cascade-delete via the relationship.
        for run in definition.runs:
            run.job_definition_id = None
        db.session.delete(definition)
        db.session.commit()
        return "", 204
