from celery.result import AsyncResult
from flask import jsonify
from flask.views import MethodView


class JobStatusView(MethodView):
    def get(self, task_id: str):
        result = AsyncResult(task_id)
        return jsonify(
            {
                "task_id": task_id,
                "state": result.state,
                "info": result.info
                if isinstance(result.info, dict)
                else str(result.info),
            }
        )
