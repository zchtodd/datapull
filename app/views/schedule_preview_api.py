from flask import jsonify, request
from flask.views import MethodView

from app.decorators import admin_required
from app.filters import humanize_cron
from app.scheduling import humanize_until, next_run_at


class SchedulePreviewAPI(MethodView):
    """Admin JSON API: describe a cron string the schedule builder produced.

    Single source of truth for the human text (same helpers the grid uses) so
    the builder preview matches what's shown after saving.
    """

    decorators = [admin_required]

    def get(self):
        from croniter import croniter

        cron = (request.args.get("cron") or "").strip() or None
        if cron is None:
            return jsonify(
                {"valid": True, "human": "Manual", "next_run": None, "next_run_human": None}
            )
        if not croniter.is_valid(cron):
            return jsonify({"valid": False, "human": None, "next_run": None, "next_run_human": None})

        nxt = next_run_at(cron)
        return jsonify(
            {
                "valid": True,
                "human": humanize_cron(cron),
                "next_run": nxt.isoformat() if nxt else None,
                "next_run_human": humanize_until(nxt),
            }
        )
