"""Jinja template filters."""
from cron_descriptor import get_description
from flask import Flask

from app.scheduling import humanize_until


def humanize_cron(expression: str | None) -> str:
    """Render a cron expression as human-friendly text.

    Returns "Manual" when there is no schedule, and falls back to the raw
    expression if it can't be parsed.
    """
    if not expression:
        return "Manual"
    try:
        return get_description(expression)
    except Exception:
        return expression


def register_filters(app: Flask) -> None:
    app.add_template_filter(humanize_cron, "cron_human")
    app.add_template_filter(humanize_until, "until")
