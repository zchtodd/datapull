"""Runtime API for job-reported failures (token-authenticated, scoped to the
run). A running job records a unit of work it couldn't complete; the platform
surfaces these on the run page."""
from flask import g, jsonify, request
from flask.views import MethodView

from app.runtime.auth import run_token_required
from app.runtime.failures import record_failure, serialize_failure


class RuntimeFailureCollectionAPI(MethodView):
    """Job reports a unit of work it couldn't complete."""

    decorators = [run_token_required]

    def post(self):
        data = request.get_json(silent=True) or {}
        item = (data.get("item") or "").strip()
        if not item:
            return jsonify({"error": "item is required."}), 400
        f = record_failure(
            g.runtime_run.id,
            item,
            kind=(data.get("kind") or "").strip(),
            label=(data.get("label") or "").strip() or None,
            detail=(data.get("detail") or "").strip() or None,
            evidence=(data.get("evidence") or "").strip() or None,
        )
        return jsonify(serialize_failure(f)), 201
