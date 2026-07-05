from flask import jsonify, request
from flask.views import MethodView

from app.tasks import long_running_job


class StartJobView(MethodView):
    def post(self):
        seconds = int(request.args.get("seconds", 10))
        result = long_running_job.delay(seconds)
        return jsonify({"task_id": result.id}), 202
