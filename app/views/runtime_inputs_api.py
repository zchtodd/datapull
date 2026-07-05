"""Runtime API used by a running job's SDK (token-authenticated, scoped to the
run). The job creates an input request and polls it; the platform resolves it
via the automated provider and/or an operator in the UI.
"""
from flask import g, jsonify, request
from flask.views import MethodView

from app.extensions import db
from app.models import JobInputRequest
from app.models.job_input_request import FULFILLED
from app.runtime.auth import run_token_required
from app.runtime.inputs import open_request, serialize_input_request, try_auto_resolve


class RuntimeInputCollectionAPI(MethodView):
    """Job asks the platform for a value it needs mid-run."""

    decorators = [run_token_required]

    def post(self):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name is required."}), 400
        kind = (data.get("kind") or "text").strip()
        prompt = (data.get("prompt") or "").strip()
        req = open_request(g.runtime_run.id, name, kind, prompt)
        return jsonify(serialize_input_request(req)), 201


class RuntimeInputItemAPI(MethodView):
    """Job polls one request; we attempt automated resolution on each poll and
    return the value once fulfilled (only to the owning run)."""

    decorators = [run_token_required]

    def get(self, request_id: int):
        req = db.session.get(JobInputRequest, request_id)
        if req is None or req.job_run_id != g.runtime_run.id:
            return jsonify({"error": "Input request not found."}), 404
        if req.is_open:
            try_auto_resolve(req)
        body = serialize_input_request(req)
        body["value"] = req.value if req.status == FULFILLED else None
        return jsonify(body)
