"""Entry point for the Celery worker: `celery -A celery_worker.celery_app worker`."""
from app import create_app

flask_app = create_app()
celery_app = flask_app.extensions["celery"]
