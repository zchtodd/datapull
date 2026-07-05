"""Runtime API for a running job to report progress (token-authenticated,
scoped to the run). The job sets its total work once, then advances as it goes."""
from flask import g, jsonify, request
from flask.views import MethodView

from app.runtime.auth import run_token_required
from app.runtime.progress import serialize_progress, update_progress


class RuntimeProgressAPI(MethodView):
    decorators = [run_token_required]

    def get(self):
        return jsonify(serialize_progress(g.runtime_run))

    def post(self):
        data = request.get_json(silent=True) or {}

        def as_int(key):
            v = data.get(key)
            if v is None:
                return None
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        update_progress(
            g.runtime_run,
            total=as_int("total"),
            current=as_int("current"),
            advance=as_int("advance"),
            message=data.get("message"),
        )
        return jsonify(serialize_progress(g.runtime_run))
