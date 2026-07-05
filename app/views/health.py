from flask import jsonify
from flask.views import MethodView


class HealthView(MethodView):
    def get(self):
        return jsonify({"status": "ok"})
