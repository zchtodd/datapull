"""Zip-and-stream the user-facing downloads of a run or a whole batch.

System artifacts (logs, manifest, failure dumps) are excluded — this bundles
only the deliverables. The zip is built to a temp file and streamed; on Linux
the file is safely unlinked while still open, so it cleans itself up.
"""
import os
import tempfile
import zipfile

from flask import abort, after_this_request, current_app, send_file
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobRun, JobRunBatch


def _safe_component(text: str) -> str:
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in text).strip()


def _add_run_outputs(zf, run, outputs_dir, arc_prefix=""):
    """Add a run's download-category files to the open zip, preserving the
    per-result folder structure (the run_<id>/ prefix is stripped). Returns the
    number of files added."""
    added = 0
    for o in run.outputs:
        if o.is_system:
            continue
        full = os.path.join(outputs_dir, o.storage_path)
        if not os.path.isfile(full):
            continue
        # storage_path is "run_<id>/<nested deliverable path>"; drop the run dir.
        rel = o.storage_path.split(os.sep, 1)[-1] if os.sep in o.storage_path \
            else o.storage_path
        arcname = os.path.join(arc_prefix, rel) if arc_prefix else rel
        zf.write(full, arcname)
        added += 1
    return added


def _stream_zip(runs, download_name, prefix_per_run=False):
    """Build a zip of the given runs' downloads and stream it as an attachment.
    404s if there are no deliverables to bundle."""
    outputs_dir = current_app.config["OUTPUTS_DIR"]
    tmp = tempfile.NamedTemporaryFile(prefix="datapull_dl_", suffix=".zip",
                                      delete=False)
    try:
        total = 0
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for run in runs:
                prefix = ""
                if prefix_per_run:
                    prefix = _safe_component(run.client_label or f"run_{run.id}")
                total += _add_run_outputs(zf, run, outputs_dir, prefix)
        tmp.close()
    except Exception:
        tmp.close()
        _quiet_unlink(tmp.name)
        raise

    if total == 0:
        _quiet_unlink(tmp.name)
        abort(404, "No downloads available for this run.")

    @after_this_request
    def _cleanup(response):
        _quiet_unlink(tmp.name)
        return response

    return send_file(tmp.name, as_attachment=True, download_name=download_name,
                     mimetype="application/zip")


def _quiet_unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass


class RunDownloadsZipView(MethodView):
    """Download all of a single run's deliverables as one zip."""

    decorators = [login_required]

    def get(self, run_id: int):
        run = db.get_or_404(JobRun, run_id)
        return _stream_zip([run], f"run-{run.id}-downloads.zip")


class BatchDownloadsZipView(MethodView):
    """Download every client run's deliverables in a batch as one zip, each
    run's files namespaced by client so they don't collide."""

    decorators = [login_required]

    def get(self, batch_id: int):
        batch = db.get_or_404(JobRunBatch, batch_id)
        multi = len(batch.runs) > 1
        return _stream_zip(batch.runs, f"batch-{batch.id}-downloads.zip",
                           prefix_per_run=multi)
