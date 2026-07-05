from celery import Celery, Task
from flask import Flask

# Load a local .env into os.environ before config/secrets are read. This makes
# non-Docker entry points (gunicorn, `python wsgi.py`, the celery worker) pick
# up .env the way the Flask CLI already does. Real environment variables take
# precedence (load_dotenv won't override them), so Docker/Compose is unaffected.
# Guarded so a not-yet-rebuilt image without the package still imports cleanly.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ModuleNotFoundError:
    pass

from app.config import Config
from app.extensions import db, login_manager, migrate


def celery_init_app(app: Flask) -> Celery:
    """Create a Celery app whose tasks run inside the Flask app context.

    Follows the pattern from the official Flask + Celery documentation:
    https://flask.palletsprojects.com/en/stable/patterns/celery/
    """

    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    # Import models so their metadata is registered before migrate.init_app.
    from app import models  # noqa: F401
    from app.models import User

    migrate.init_app(app, db)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    celery_init_app(app)

    # Ensure task modules are imported so Celery registers them.
    from app import tasks  # noqa: F401
    from app.cli import register_cli
    from app.filters import register_filters
    from app.views import api, bp

    app.register_blueprint(bp)
    app.register_blueprint(api)
    register_cli(app)
    register_filters(app)

    # WebSocket endpoints (live browser view) — only in processes that serve
    # HTTP (web). The Celery worker also builds the app but never serves WS and
    # may not have flask-sock installed, so this is best-effort.
    try:
        from flask_sock import Sock

        from app.runtime.live import register_live

        register_live(Sock(app))
    except ModuleNotFoundError:
        app.logger.info("flask-sock not installed; live-view WebSocket disabled")

    return app
