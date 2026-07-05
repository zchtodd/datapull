from flask import jsonify, request
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobInputRequest, JobRun
from app.models.job_input_request import PENDING
from app.runtime.inputs import fulfill, serialize_input_request


class JobRunInputsAPI(MethodView):
    """List a run's open input requests (the operator console polls this)."""

    decorators = [login_required]

    def get(self, run_id: int):
        run = db.get_or_404(JobRun, run_id)
        pending = [
            serialize_input_request(r) for r in run.input_requests if r.is_open
        ]
        return jsonify({"inputs": pending})


class JobInputFulfillAPI(MethodView):
    """Operator supplies the value for one pending input request."""

    decorators = [login_required]

    def post(self, request_id: int):
        req = db.get_or_404(JobInputRequest, request_id)
        if req.status != PENDING:
            return jsonify({"error": f"This input is already {req.status.lower()}."}), 409
        data = request.get_json(silent=True) or {}
        value = (data.get("value") or "").strip()
        if not value:
            return jsonify({"error": "A value is required."}), 400
        fulfill(req, value, source="operator")
        return jsonify(serialize_input_request(req))
