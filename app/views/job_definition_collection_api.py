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


class JobDefinitionCollectionAPI(MethodView):
    """Admin JSON API: list and create job definitions."""

    decorators = [admin_required]

    def get(self):
        defs = db.session.scalars(
            db.select(JobDefinition).order_by(JobDefinition.name)
        ).all()
        return jsonify({"job_definitions": [serialize_job_definition(d) for d in defs]})

    def post(self):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        script_path = (data.get("script_path") or "").strip()
        description = (data.get("description") or "").strip()
        schedule = (data.get("schedule") or "").strip() or None
        is_enabled = bool(data.get("is_enabled", True))
        auto_resume_enabled = bool(data.get("auto_resume_enabled", False))
        auto_resume_max_attempts = clamp_auto_resume_attempts(
            data.get("auto_resume_max_attempts"))

        error = validate_job_definition(name, script_path, description, schedule)
        if error:
            return jsonify({"error": error}), 400
        if db.session.scalar(db.select(JobDefinition).filter_by(name=name)):
            return jsonify({"error": f"A job named '{name}' already exists."}), 409

        definition = JobDefinition(
            name=name,
            script_path=script_path,
            description=description,
            schedule=schedule,
            is_enabled=is_enabled,
            auto_resume_enabled=auto_resume_enabled,
            auto_resume_max_attempts=auto_resume_max_attempts,
        )
        bind_err = apply_definition_connections(definition, data.get("connection_ids"))
        if bind_err:
            return jsonify({"error": bind_err}), 400
        db.session.add(definition)
        db.session.commit()
        return jsonify(serialize_job_definition(definition)), 201
