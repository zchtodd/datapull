"""Serve the latest live-view screenshot for a run. The job writes frames to a
shared path; the run/dashboard UI shows this image and refreshes it every couple
of seconds — the cross-platform replacement for the old container VNC bridge."""
import os

from flask import Response, send_file
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRun
from app.runtime.launcher import live_frame_path


class RunLiveFrameView(MethodView):
    """GET the newest live frame (JPEG) for a run, or 204 if none captured yet."""

    decorators = [login_required]

    def get(self, run_id: int):
        db.get_or_404(JobRun, run_id)
        path = live_frame_path(run_id)
        if not os.path.exists(path):
            return Response(status=204)  # no frame yet
        resp = send_file(path, mimetype="image/jpeg", max_age=0)
        resp.headers["Cache-Control"] = "no-store"
        return resp
