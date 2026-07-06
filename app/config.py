import os

# The application database URL, shared by SQLAlchemy and (by default) the Celery
# broker + result backend. Defaults to the docker-compose `db` service; override
# DATABASE_URL to point elsewhere (external SQL Server, SQLite, ...).
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mssql+pyodbc://sa:Datapull_Dev_Pass123@localhost:1433/datapull"
    "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes",
)

BROKER_URL = os.environ.get("CELERY_BROKER_URL", "sqla+" + DATABASE_URL)
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "db+" + DATABASE_URL)


def _broker_transport_options():
    """Long browser jobs must not be redelivered mid-run (a duplicate would
    fight the live run). For virtual transports (Redis/SQS) that's the
    visibility_timeout, set generously (> the 24h run cap).

    The SQLAlchemy transport does NOT accept it: it forwards broker_transport_
    options straight to create_engine(), which rejects visibility_timeout. So we
    omit it for the DB broker and instead rely on the launcher's DuplicateRun
    guard (a live run's PID/container) to no-op any redelivery."""
    if BROKER_URL.startswith(("sqla", "sqlalchemy")):
        return {}
    return {
        "visibility_timeout": int(
            os.environ.get("CELERY_VISIBILITY_TIMEOUT", str(26 * 3600)))
    }


class Config:
    """Base application configuration, populated from environment variables."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")

    # SQLAlchemy / SQL Server via pyodbc + Microsoft ODBC Driver 18.
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Base directory under which job-run output files are stored and served.
    OUTPUTS_DIR = os.environ.get("OUTPUTS_DIR", os.path.abspath("outputs"))

    # Celery reads its settings from the `CELERY` key on the Flask config.
    # See app/__init__.py where this is handed to the Celery instance.
    #
    # Default broker + results live on the application database — no separate
    # broker service (Redis/Memurai/RabbitMQ) to install or run. kombu's
    # SQLAlchemy transport ("sqla+") is the broker; Celery's database result
    # backend ("db+") stores results. docker-compose sets CELERY_BROKER_URL to
    # redis for dev, which overrides these; native/prod uses the DB default.
    CELERY = {
        "broker_url": BROKER_URL,
        "result_backend": RESULT_BACKEND,
        # Don't ack a task until it finishes, so a crashed worker's task is
        # redelivered rather than lost (see _broker_transport_options re: the
        # redelivery window).
        "task_acks_late": True,
        "worker_prefetch_multiplier": 1,
        "broker_transport_options": _broker_transport_options(),
        "task_track_started": True,
        # Celery Beat: tick once a minute; the task enqueues any due jobs.
        "beat_schedule": {
            "scheduler-tick": {
                "task": "app.tasks.scheduler_tick",
                "schedule": 60.0,
            },
        },
    }
