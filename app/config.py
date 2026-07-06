import os

# The application database URL, shared by SQLAlchemy and (by default) the Celery
# broker + result backend. Defaults to the docker-compose `db` service; override
# DATABASE_URL to point elsewhere (external SQL Server, SQLite, ...).
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mssql+pyodbc://sa:Datapull_Dev_Pass123@localhost:1433/datapull"
    "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes",
)


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
        "broker_url": os.environ.get("CELERY_BROKER_URL", "sqla+" + DATABASE_URL),
        "result_backend": os.environ.get(
            "CELERY_RESULT_BACKEND", "db+" + DATABASE_URL
        ),
        # Long browser jobs: don't ack a task until it finishes, and give it a
        # generous window before the broker considers it lost and redelivers.
        # The visibility timeout MUST exceed the longest a run can take
        # (DATAPULL_RUN_TIMEOUT_S, incl. multi-hour MFA waits) — otherwise the
        # broker redelivers a still-running task and a duplicate kills the live
        # run and clobbers its output. Honored by both the Redis and SQLAlchemy
        # (virtual) transports. Default 26h > the 24h run cap.
        "task_acks_late": True,
        "worker_prefetch_multiplier": 1,
        "broker_transport_options": {
            "visibility_timeout": int(
                os.environ.get("CELERY_VISIBILITY_TIMEOUT", str(26 * 3600)))
        },
        "task_track_started": True,
        # Celery Beat: tick once a minute; the task enqueues any due jobs.
        "beat_schedule": {
            "scheduler-tick": {
                "task": "app.tasks.scheduler_tick",
                "schedule": 60.0,
            },
        },
    }
