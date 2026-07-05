"""View decorators for access control."""
from functools import wraps

from flask import abort
from flask_login import current_user

from app.extensions import login_manager


def admin_required(view):
    """Require an authenticated admin user.

    Unauthenticated users are sent through the login flow; authenticated
    non-admins get a 403. Self-contained so it can be used alone in a view's
    `decorators` list without caring about ordering.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped
