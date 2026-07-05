from flask import jsonify, request
from flask.views import MethodView

from app.decorators import admin_required
from app.extensions import db
from app.models import Connection, JobDefinition, JobDefinitionConnection
from app.services import serialize_connection, validate_connection


class ConnectionItemAPI(MethodView):
    """Admin JSON API: update and delete a single connection."""

    decorators = [admin_required]

    def patch(self, connection_id: int):
        conn = db.get_or_404(Connection, connection_id)
        data = request.get_json(silent=True) or {}

        name = (data.get("name", conn.name) or "").strip()
        is_mfa = bool(data.get("is_mfa", conn.is_mfa))
        is_shared = bool(data.get("is_shared", conn.is_shared))
        description = (data.get("description", conn.description) or "").strip()

        error = validate_connection(name)
        if error:
            return jsonify({"error": error}), 400
        clash = db.session.scalar(
            db.select(Connection).where(
                Connection.name == name, Connection.id != conn.id
            )
        )
        if clash:
            return jsonify({"error": f"A connection named '{name}' already exists."}), 409

        conn.name = name
        conn.is_mfa = is_mfa
        conn.is_shared = is_shared
        conn.description = description
        db.session.commit()
        return jsonify(serialize_connection(conn))

    def delete(self, connection_id: int):
        conn = db.get_or_404(Connection, connection_id)
        # Don't orphan job bindings: refuse while any job still references it.
        bindings = db.session.scalars(
            db.select(JobDefinitionConnection)
            .where(JobDefinitionConnection.connection_id == conn.id)
        ).all()
        if bindings:
            jobs = sorted({b.job_definition.name for b in bindings})
            names = ", ".join(jobs[:5])
            more = "" if len(jobs) <= 5 else f" (+{len(jobs) - 5} more)"
            return jsonify({
                "error": f"In use by job(s): {names}{more}. Unbind them first."
            }), 409
        db.session.delete(conn)  # parameters cascade-delete
        db.session.commit()
        return "", 204
