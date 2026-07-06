"""Runtime API for key-based completion checkpoints (token-authenticated,
scoped to the run's job definition). A job marks keys done and queries them to
decide whether to skip or do a unit of work."""
from flask import g, jsonify, request
from flask.views import MethodView

from app.runtime.auth import run_token_required
from app.runtime.checkpoints import checkpoint_status, done_keys, mark_checkpoint


class RuntimeCheckpointAPI(MethodView):
    decorators = [run_token_required]

    def get(self):
        """?namespace=NS -> {"keys": [...]} (the done set);
        ?namespace=NS&key=K -> {"key","namespace","status"} (one key)."""
        defn = g.runtime_run.job_definition_id
        namespace = request.args.get("namespace", "")
        key = request.args.get("key")
        # A "from scratch" run ignores checkpoints: report nothing done so the
        # job re-does all work. (It still POSTs completions for future runs.)
        if defn is None or g.runtime_run.from_scratch:
            return jsonify({"keys": []} if key is None else
                           {"key": key, "namespace": namespace, "status": None})
        if key is not None:
            return jsonify({"key": key, "namespace": namespace,
                            "status": checkpoint_status(defn, namespace, key)})
        return jsonify({"keys": done_keys(defn, namespace)})

    def post(self):
        """Mark a key: {namespace, key, status="DONE"}."""
        data = request.get_json(silent=True) or {}
        key = (data.get("key") or "").strip()
        if not key:
            return jsonify({"error": "key is required."}), 400
        defn = g.runtime_run.job_definition_id
        if defn is None:
            return jsonify({"error": "This run has no job definition."}), 400
        namespace = (data.get("namespace") or "").strip()
        status = (data.get("status") or "DONE").strip()
        cp = mark_checkpoint(defn, namespace, key, status)
        return jsonify({"key": cp.key, "namespace": cp.namespace, "status": cp.status})
