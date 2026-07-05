"""SQLAlchemy models.

Each model lives in its own module; they are re-exported here so that
`from app.models import User, JobDefinition` works and importing the package
registers all tables on the shared metadata (needed by Flask-Migrate autogenerate).
"""
from app.models.connection import (
    Connection,
    ConnectionParameter,
    JobDefinitionConnection,
    JobRunConnection,
)
from app.models.job_checkpoint import JobCheckpoint
from app.models.job_definition import JobDefinition
from app.models.job_input_request import JobInputRequest
from app.models.job_parameter import JobParameter
from app.models.job_run import JobRun
from app.models.job_run_batch import JobRunBatch
from app.models.job_run_failure import JobRunFailure
from app.models.job_run_output import JobRunOutput
from app.models.user import Role, User

__all__ = [
    "Connection",
    "ConnectionParameter",
    "JobDefinitionConnection",
    "JobRunConnection",
    "JobCheckpoint",
    "JobDefinition",
    "JobInputRequest",
    "JobParameter",
    "JobRun",
    "JobRunBatch",
    "JobRunFailure",
    "JobRunOutput",
    "Role",
    "User",
]
