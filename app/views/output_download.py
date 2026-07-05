from flask import current_app, send_from_directory
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRunOutput


class OutputDownloadView(MethodView):
    """Download a single job-run output file as an attachment."""

    decorators = [login_required]

    def get(self, output_id: int):
        output = db.get_or_404(JobRunOutput, output_id)
        # send_from_directory safely resolves storage_path within OUTPUTS_DIR
        # (rejecting path traversal) and 404s if the file is missing.
        return send_from_directory(
            current_app.config["OUTPUTS_DIR"],
            output.storage_path,
            as_attachment=True,
            download_name=output.filename,
        )
