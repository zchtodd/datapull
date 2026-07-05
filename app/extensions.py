"""Shared Flask extension instances, initialized in the app factory."""
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
# Unauthenticated users hitting a @login_required view are redirected here.
login_manager.login_view = "main.login"
