from flask import render_template
from flask.views import MethodView
from flask_login import login_required

from app.extensions import db
from app.models import JobDefinition, JobRunBatch
from app.models.job_run import RUNNING_STATUSES


class IndexView(MethodView):
    """Dashboard: one card per job definition. The activity strip shows recent
    executions (batches) with a rollup status; cells link to the batch detail."""

    decorators = [login_required]

    # How many recent executions to show in the activity strip.
    HISTORY_LIMIT = 30

    def get(self):
        definitions = db.session.scalars(
            db.select(JobDefinition).order_by(JobDefinition.name)
        ).all()
        cards = []
        for definition in definitions:
            recent = db.session.scalars(
                db.select(JobRunBatch)
                .filter_by(job_definition_id=definition.id)
                .order_by(JobRunBatch.created_at.desc())
                .limit(self.HISTORY_LIMIT)
            ).all()
            history = list(reversed(recent))
            cells = [None] * (self.HISTORY_LIMIT - len(history)) + history
            batch = recent[0] if recent else None
            # Representative child for the card's live-view / MFA / outputs:
            # a running child if any, else the most recent child.
            run = None
            output_count = 0
            if batch and batch.runs:
                running = [r for r in batch.runs if r.status in RUNNING_STATUSES]
                run = running[0] if running else batch.runs[-1]
                # Outputs of a batch are spread across its client runs, so the
                # card shows a total count linking to the detail view rather
                # than an (often huge) per-file list. Count only user-facing
                # downloads — system artifacts (logs, manifest, failure dumps)
                # don't belong in the headline number.
                output_count = sum(
                    1 for r in batch.runs for o in r.outputs if not o.is_system
                )
            cards.append(
                {"definition": definition, "batch": batch, "run": run,
                 "cells": cells, "output_count": output_count}
            )
        return render_template("index.html", cards=cards)
