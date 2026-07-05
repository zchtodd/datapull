"""URL routing: blueprints plus class-based view registration.

Each view class lives in its own module; this package wires them to routes.
"""
from flask import Blueprint

from app.views.active_runs_api import ActiveRunsAPI
from app.views.batch_detail import BatchDetailView
from app.views.connection_brief_api import ConnectionBriefListAPI
from app.views.connection_collection_api import ConnectionCollectionAPI
from app.views.connection_item_api import ConnectionItemAPI
from app.views.connection_list import ConnectionListView
from app.views.connection_parameter_collection_api import (
    ConnectionParameterCollectionAPI,
)
from app.views.connection_parameter_item_api import ConnectionParameterItemAPI
from app.views.downloads_zip import BatchDownloadsZipView, RunDownloadsZipView
from app.views.health import HealthView
from app.views.index import IndexView
from app.views.job_definition_collection_api import JobDefinitionCollectionAPI
from app.views.job_definition_detail import JobDefinitionDetailView
from app.views.job_definition_item_api import JobDefinitionItemAPI
from app.views.job_definition_list import JobDefinitionListView
from app.views.job_kill import JobKillView
from app.views.job_resume import JobResumeView
from app.views.job_parameter_collection_api import JobParameterCollectionAPI
from app.views.job_parameter_item_api import JobParameterItemAPI
from app.views.job_run_inputs_api import JobInputFulfillAPI, JobRunInputsAPI
from app.views.job_run_list_api import JobRunListView
from app.views.job_start import JobStartView
from app.views.job_status import JobStatusView
from app.views.login import LoginView
from app.views.logout import LogoutView
from app.views.output_download import OutputDownloadView
from app.views.run_detail import RunDetailView, RunStdoutView
from app.views.run_outputs_api import RunOutputsAPI
from app.views.runtime_checkpoints_api import RuntimeCheckpointAPI
from app.views.runtime_failures_api import RuntimeFailureCollectionAPI
from app.views.runtime_inputs_api import RuntimeInputCollectionAPI, RuntimeInputItemAPI
from app.views.runtime_progress_api import RuntimeProgressAPI
from app.views.schedule_preview_api import SchedulePreviewAPI
from app.views.start_job import StartJobView

# Server-rendered web UI.
bp = Blueprint("main", __name__)
bp.add_url_rule("/", view_func=IndexView.as_view("index"))
bp.add_url_rule("/login", view_func=LoginView.as_view("login"))
bp.add_url_rule("/logout", view_func=LogoutView.as_view("logout"))
bp.add_url_rule(
    "/admin/job-definitions",
    view_func=JobDefinitionListView.as_view("job_definition_list"),
)
bp.add_url_rule(
    "/admin/job-definitions/<int:definition_id>",
    view_func=JobDefinitionDetailView.as_view("job_definition_detail"),
)
bp.add_url_rule(
    "/outputs/<int:output_id>/download",
    view_func=OutputDownloadView.as_view("output_download"),
)
bp.add_url_rule(
    "/jobs/<int:definition_id>/start",
    view_func=JobStartView.as_view("job_start"),
)
bp.add_url_rule(
    "/jobs/<int:definition_id>/kill",
    view_func=JobKillView.as_view("job_kill"),
)
bp.add_url_rule(
    "/runs/<int:run_id>/resume",
    view_func=JobResumeView.as_view("job_resume"),
)
bp.add_url_rule(
    "/batches/<int:batch_id>",
    view_func=BatchDetailView.as_view("batch_detail"),
)
bp.add_url_rule(
    "/runs/<int:run_id>",
    view_func=RunDetailView.as_view("run_detail"),
)
bp.add_url_rule(
    "/runs/<int:run_id>/stdout",
    view_func=RunStdoutView.as_view("run_stdout"),
)
bp.add_url_rule(
    "/runs/<int:run_id>/downloads.zip",
    view_func=RunDownloadsZipView.as_view("run_downloads_zip"),
)
bp.add_url_rule(
    "/batches/<int:batch_id>/downloads.zip",
    view_func=BatchDownloadsZipView.as_view("batch_downloads_zip"),
)
bp.add_url_rule(
    "/admin/connections",
    view_func=ConnectionListView.as_view("connection_list"),
)

# JSON API, mounted under /api.
api = Blueprint("api", __name__, url_prefix="/api")
api.add_url_rule("/health", view_func=HealthView.as_view("health"))
api.add_url_rule("/jobs", view_func=StartJobView.as_view("start_job"))
api.add_url_rule("/jobs/<task_id>", view_func=JobStatusView.as_view("job_status"))
api.add_url_rule("/job-runs", view_func=JobRunListView.as_view("job_run_list"))
api.add_url_rule("/job-runs/active", view_func=ActiveRunsAPI.as_view("active_runs"))
api.add_url_rule(
    "/connections", view_func=ConnectionBriefListAPI.as_view("connection_brief_list")
)
api.add_url_rule(
    "/job-runs/<int:run_id>/inputs",
    view_func=JobRunInputsAPI.as_view("job_run_inputs"),
)
api.add_url_rule(
    "/job-runs/<int:run_id>/outputs",
    view_func=RunOutputsAPI.as_view("run_outputs"),
)
api.add_url_rule(
    "/job-inputs/<int:request_id>/fulfill",
    view_func=JobInputFulfillAPI.as_view("job_input_fulfill"),
)
# Runtime API for running jobs' SDK (per-run token auth, not login).
api.add_url_rule(
    "/runtime/inputs",
    view_func=RuntimeInputCollectionAPI.as_view("runtime_input_collection"),
)
api.add_url_rule(
    "/runtime/inputs/<int:request_id>",
    view_func=RuntimeInputItemAPI.as_view("runtime_input_item"),
)
api.add_url_rule(
    "/runtime/progress",
    view_func=RuntimeProgressAPI.as_view("runtime_progress"),
)
api.add_url_rule(
    "/runtime/checkpoints",
    view_func=RuntimeCheckpointAPI.as_view("runtime_checkpoints"),
)
api.add_url_rule(
    "/runtime/failures",
    view_func=RuntimeFailureCollectionAPI.as_view("runtime_failures"),
)
api.add_url_rule(
    "/admin/job-definitions",
    view_func=JobDefinitionCollectionAPI.as_view("job_definition_collection"),
)
api.add_url_rule(
    "/admin/job-definitions/<int:definition_id>",
    view_func=JobDefinitionItemAPI.as_view("job_definition_item"),
)
api.add_url_rule(
    "/admin/schedule-preview",
    view_func=SchedulePreviewAPI.as_view("schedule_preview"),
)
api.add_url_rule(
    "/admin/job-definitions/<int:definition_id>/parameters",
    view_func=JobParameterCollectionAPI.as_view("job_parameter_collection"),
)
api.add_url_rule(
    "/admin/job-parameters/<int:parameter_id>",
    view_func=JobParameterItemAPI.as_view("job_parameter_item"),
)
api.add_url_rule(
    "/admin/connections",
    view_func=ConnectionCollectionAPI.as_view("connection_collection"),
)
api.add_url_rule(
    "/admin/connections/<int:connection_id>",
    view_func=ConnectionItemAPI.as_view("connection_item"),
)
api.add_url_rule(
    "/admin/connections/<int:connection_id>/parameters",
    view_func=ConnectionParameterCollectionAPI.as_view("connection_parameter_collection"),
)
api.add_url_rule(
    "/admin/connection-parameters/<int:parameter_id>",
    view_func=ConnectionParameterItemAPI.as_view("connection_parameter_item"),
)

__all__ = ["api", "bp"]
