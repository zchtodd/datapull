"""Shared logic for job-definition / connection serialization and validation."""
import json
import logging
from datetime import datetime, timedelta, timezone

from croniter import croniter

from app.extensions import db
from app.filters import humanize_cron
from app.models import Connection, JobDefinition, JobDefinitionConnection
from app.models.parameter import VALUE_TYPES
from sdk.datapull_runtime import (
    EXIT_FORBIDDEN, EXIT_LOGIN, EXIT_MFA, EXIT_UNEXPECTED)

log = logging.getLogger("datapull.services")

# Platform-observed exit sentinels, for runs that ended without a job exit code
# of their own (negative, so they never collide with a job's 0..N codes). A run
# that reached a terminal state always has a non-null exit_code: either the
# job's code or one of these.
EXIT_WORKER_ERROR = -2    # the worker/launcher raised before the job exited
EXIT_NO_DEFINITION = -3   # the dispatched run had no job definition to launch

# Platform policy: which exit codes are worth auto-resuming. EXIT_UNEXPECTED
# (often transient), EXIT_LOGIN (e.g. the cert/cookies class), EXIT_MFA (MFA
# timeout / session expired), and EXIT_WORKER_ERROR (a launch hiccup/teardown)
# retry on the default schedule; EXIT_FORBIDDEN (403 — often a temporary block)
# retries on a longer schedule (see below). EXIT_CONFIG and EXIT_NO_DEFINITION
# are deterministic and never auto-resumed.
RETRYABLE_EXIT_CODES = frozenset(
    {EXIT_UNEXPECTED, EXIT_LOGIN, EXIT_MFA, EXIT_FORBIDDEN, EXIT_WORKER_ERROR})

# Backoff (seconds) before the Nth auto-resume attempt — gives a transient
# outage time to clear and avoids hammering the portal. A 403 (EXIT_FORBIDDEN)
# usually needs longer to lift, so it waits 10m -> 30m -> 1h instead of the
# default 2m -> 10m -> 30m.
_AUTO_RESUME_BACKOFF = {1: 120, 2: 600, 3: 1800}
_AUTO_RESUME_BACKOFF_FORBIDDEN = {1: 600, 2: 1800, 3: 3600}


def auto_resume_delay(attempt: int, exit_code=None) -> int:
    schedule = (_AUTO_RESUME_BACKOFF_FORBIDDEN if exit_code == EXIT_FORBIDDEN
                else _AUTO_RESUME_BACKOFF)
    # Past the mapped attempts, hold at the longest interval.
    return schedule.get(attempt, max(schedule.values()))


def clamp_auto_resume_attempts(value, default=3) -> int:
    """Coerce a submitted max-attempts value into the allowed 1..10 range."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(10, n))


def resolve_connection_ids(raw_ids) -> tuple[list[int], str | None]:
    """Validate a list of connection ids. Returns (ids, error)."""
    if raw_ids is None:
        return [], None
    if not isinstance(raw_ids, (list, tuple)):
        return [], "connection_ids must be a list."
    ids = []
    for raw in raw_ids:
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            return [], f"Invalid connection id {raw!r}."
        if db.session.get(Connection, cid) is None:
            return [], f"Connection {cid} no longer exists."
        if cid not in ids:
            ids.append(cid)
    return ids, None


def apply_definition_connections(definition: JobDefinition, raw_ids) -> str | None:
    """Replace a definition's attached connections from a list of ids.
    Returns an error message, or None on success. Caller commits."""
    ids, err = resolve_connection_ids(raw_ids)
    if err:
        return err
    # Remove existing attachments and flush the DELETEs before inserting new
    # ones, or re-attaching the same connection trips the (job, conn) unique key.
    had_existing = bool(definition.connection_bindings)
    definition.connection_bindings[:] = []
    if had_existing:
        db.session.flush()
    for cid in ids:
        definition.connection_bindings.append(
            JobDefinitionConnection(connection_id=cid)
        )
    return None


def serialize_job_definition(d: JobDefinition) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "script_path": d.script_path,
        "schedule": d.schedule,
        "schedule_human": humanize_cron(d.schedule),
        "is_enabled": d.is_enabled,
        "auto_resume_enabled": d.auto_resume_enabled,
        "auto_resume_max_attempts": d.auto_resume_max_attempts,
        "connections": [
            {"id": b.connection_id,
             "name": b.connection.name if b.connection else None,
             "is_mfa": b.connection.is_mfa if b.connection else False}
            for b in d.connection_bindings
        ],
    }


def validate_job_definition(
    name: str, script_path: str, description: str, schedule: str | None
) -> str | None:
    """Return an error message if the fields are invalid, else None."""
    if not name:
        return "Name is required."
    if not script_path:
        return "Script path is required."
    if not description:
        return "Description is required."
    if schedule and not croniter.is_valid(schedule):
        return "Schedule is not a valid cron expression."
    return None


def serialize_parameter(p) -> dict:
    """Serialize a JobParameter or ConnectionParameter for the API.

    Non-secret values are revealed (so they're viewable/editable); secret values
    are never returned — `has_value` lets the UI show a masked placeholder.
    """
    return {
        "id": p.id,
        "key": p.key,
        "is_secret": p.is_secret,
        "value_type": p.value_type,
        "has_value": p.has_value,
        # Reveal plaintext only for non-secrets; secrets stay write-only.
        "value": None if p.is_secret else p.value,
    }


def serialize_connection(c: Connection) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "is_mfa": c.is_mfa,
        "is_shared": c.is_shared,
        "description": c.description,
        "parameter_count": len(c.parameters),
    }


def connection_config(c: Connection) -> dict:
    """Decrypt a connection's parameters into a plain {key: value} dict for a
    provider to consume. Secret values are decrypted here."""
    return {p.key: p.value for p in c.parameters}


def enqueue_batch(definition: JobDefinition, connection_ids=None, from_scratch=False):
    """Create a JobRunBatch and dispatch its child runs, fanning out over the
    attached client connections.

    Attached connections split into: shared (is_mfa or is_shared) — attached to
    every child — and clients (the rest) — one child run each. With no client
    connections it's a single child. connection_ids defaults to the definition's
    attached set. `from_scratch` forces a clean run (ignore checkpoints + skip
    seeding) on every child. Returns the JobRunBatch. Used by manual start and
    the scheduler.
    """
    import uuid

    from app.models import Connection, JobRun, JobRunBatch, JobRunConnection
    from app.tasks import run_job_definition

    if connection_ids is None:
        conns = [b.connection for b in definition.connection_bindings]
    else:
        conns = [c for c in (db.session.get(Connection, cid) for cid in connection_ids)
                 if c is not None]
    shared = [c for c in conns if c.is_mfa or c.is_shared]
    clients = [c for c in conns if not c.is_mfa and not c.is_shared]

    batch = JobRunBatch(job_definition_id=definition.id)
    db.session.add(batch)
    db.session.flush()

    # One child per client connection (+ shared); or a single child if none.
    plan = ([(shared + [client], client.name) for client in clients]
            if clients else [(shared, None)])

    dispatched = []
    for conn_set, label in plan:
        task_id = str(uuid.uuid4())
        run = JobRun(task_id=task_id, status="PENDING",
                     job_definition_id=definition.id, batch_id=batch.id,
                     client_label=label, from_scratch=from_scratch)
        db.session.add(run)
        db.session.flush()
        for c in conn_set:
            db.session.add(JobRunConnection(job_run_id=run.id, connection_id=c.id))
        dispatched.append((definition.id, run.id, task_id))
    db.session.commit()

    for def_id, run_id, task_id in dispatched:
        run_job_definition.apply_async(args=[def_id, run_id], task_id=task_id)
    return batch


def enqueue_resume(prior_run, auto=False, attempt=0):
    """Create and dispatch a new run that resumes `prior_run`: same definition,
    same connection set, with resume_from_run_id set so the launcher seeds the
    new run's output dir from the prior run's files (and pins its quarter). The
    job then skips already-completed work. Returns the new JobRunBatch.

    `auto`/`attempt` mark a server-triggered auto-resume (carrying the chain's
    attempt number); a manual resume (auto=False) resets the attempt budget to 0
    so an operator's intervention starts the retry count fresh.

    The caller guards (definition exists, prior run is terminal, no other run of
    the definition is active)."""
    import uuid

    from app.models import JobRun, JobRunBatch, JobRunConnection
    from app.tasks import run_job_definition

    definition = prior_run.job_definition
    batch = JobRunBatch(job_definition_id=definition.id)
    db.session.add(batch)
    db.session.flush()

    task_id = str(uuid.uuid4())
    run = JobRun(
        task_id=task_id, status="PENDING",
        job_definition_id=definition.id, batch_id=batch.id,
        client_label=prior_run.client_label,
        resume_from_run_id=prior_run.id,
        auto_resume_attempt=attempt if auto else 0,
        # Seed progress so the bar starts where the prior run left off (the job
        # may recompute its own total once it starts).
        progress_total=prior_run.progress_total,
        progress_current=prior_run.progress_current or 0,
    )
    db.session.add(run)
    db.session.flush()
    for jrc in prior_run.connections:
        db.session.add(JobRunConnection(job_run_id=run.id, connection_id=jrc.connection_id))
    # A resume now exists for prior_run, so any pending auto-resume countdown on
    # it is superseded — clear it so the UI stops counting and the scheduled
    # auto-resume task no-ops when it fires.
    prior_run.auto_resume_at = None
    db.session.commit()

    run_job_definition.apply_async(args=[definition.id, run.id], task_id=task_id)
    return batch


def maybe_auto_resume(run, exit_code) -> bool:
    """Decide whether a just-failed `run` should be auto-resumed and, if so,
    schedule a delayed auto-resume task and stamp `run.auto_resume_at` (drives
    the UI countdown). Returns True if scheduled. Called from the worker.

    Natural limits (all must pass): the definition opted in; the exit code is
    retryable; the per-definition attempt cap isn't reached; and the run made
    real progress over the run it resumed from (a stalled chain stops early so a
    permanent failure can't burn the whole attempt budget). A 403 (EXIT_FORBIDDEN)
    is exempt from the progress guard — it's retried purely on a timed schedule,
    since a temporary block lifts with time, not with progress."""
    from app.tasks import auto_resume_run

    definition = run.job_definition
    if definition is None or not definition.auto_resume_enabled:
        return False
    if exit_code not in RETRYABLE_EXIT_CODES:
        log.info("run %s exit=%s not retryable; no auto-resume", run.id, exit_code)
        return False
    max_attempts = definition.auto_resume_max_attempts or 0
    if run.auto_resume_attempt >= max_attempts:
        log.info("run %s reached auto-resume cap (%d); giving up",
                 run.id, max_attempts)
        return False
    # Progress-stall guard: if this run resumed another but didn't advance past
    # it, the failure isn't making headway — stop rather than loop. A 403 is
    # exempt: it retries on the timed schedule regardless of progress.
    if run.resume_from_run_id is not None and exit_code != EXIT_FORBIDDEN:
        parent = run.resume_from
        if parent is not None and (run.progress_current or 0) <= (parent.progress_current or 0):
            log.info("run %s made no progress over run %s; stopping auto-resume",
                     run.id, parent.id)
            return False

    next_attempt = run.auto_resume_attempt + 1
    delay = auto_resume_delay(next_attempt, exit_code)
    run.auto_resume_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    db.session.commit()
    auto_resume_run.apply_async(args=[run.id, next_attempt], countdown=delay)
    log.info("scheduled auto-resume attempt %d for run %s in %ds",
             next_attempt, run.id, delay)
    return True


def validate_connection(name: str) -> str | None:
    """Return an error message if the connection fields are invalid, else None."""
    if not name:
        return "Name is required."
    if len(name) > 255:
        return "Name must be 255 characters or fewer."
    return None


def validate_parameter(
    key: str, value_type: str, value: str | None
) -> str | None:
    """Return an error message if the parameter fields are invalid, else None."""
    if not key:
        return "Key is required."
    if len(key) > 255:
        return "Key must be 255 characters or fewer."
    if value_type not in VALUE_TYPES:
        return f"Unknown value type '{value_type}'."
    if value not in (None, ""):
        if value_type == "number":
            try:
                float(value)
            except (TypeError, ValueError):
                return "Value must be a number."
        elif value_type == "boolean":
            if value.strip().lower() not in ("true", "false"):
                return "Value must be 'true' or 'false'."
        elif value_type == "json":
            try:
                json.loads(value)
            except (TypeError, ValueError) as e:
                return f"Value must be valid JSON: {e}"
    return None
