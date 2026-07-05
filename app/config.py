import os


class Config:
    """Base application configuration, populated from environment variables."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")

    # SQLAlchemy / SQL Server via pyodbc + Microsoft ODBC Driver 18.
    # Defaults to the `db` service in docker-compose; override DATABASE_URL
    # to point at another instance.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "mssql+pyodbc://sa:Datapull_Dev_Pass123@localhost:1433/datapull"
        "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Base directory under which job-run output files are stored and served.
    OUTPUTS_DIR = os.environ.get("OUTPUTS_DIR", os.path.abspath("outputs"))

    # Celery reads its settings from the `CELERY` key on the Flask config.
    # See app/__init__.py where this is handed to the Celery instance.
    CELERY = {
        "broker_url": os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        "result_backend": os.environ.get(
            "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"
        ),
        # Long browser jobs: don't ack a task until it finishes, and give it a
        # generous window before the broker considers it lost and redelivers.
        # The visibility timeout MUST exceed the longest a run can take
        # (DATAPULL_RUN_TIMEOUT_S, incl. multi-hour MFA waits) — otherwise Redis
        # redelivers a still-running task and a duplicate kills the live run's
        # container and clobbers its output. Default 26h > the 24h run cap.
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
