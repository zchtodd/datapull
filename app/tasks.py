import logging
import time
from datetime import datetime

from celery import shared_task
from croniter import croniter

from app.extensions import db
from app.models import JobRun
from app.services import EXIT_NO_DEFINITION, EXIT_WORKER_ERROR
from sdk.datapull_runtime import EXIT_OK

log = logging.getLogger("datapull.tasks")


@shared_task
def scheduler_tick() -> str:
    """Fire on a fixed interval (Celery Beat). Enqueue a run for every enabled
    job definition whose cron has come due since we last checked it.

    Per definition we track `last_scheduled_at` (the cron fire-time we last
    acted on). On first sight we just baseline it — so setting a schedule never
    triggers a retroactive run — and thereafter each new slot enqueues once.
    """
    from app.models import JobDefinition
    from app.models.job_run import RUNNING_STATUSES
    from app.services import enqueue_batch

    now = datetime.utcnow()  # naive UTC; croniter base is naive -> naive results
    definitions = db.session.scalars(
        db.select(JobDefinition).where(
            JobDefinition.is_enabled == True,  # noqa: E712 (mssql wants = 1, not IS)
            JobDefinition.schedule.isnot(None),
        )
    ).all()

    fired = 0
    for d in definitions:
        try:
            prev_fire = croniter(d.schedule, now).get_prev(datetime)
        except Exception as e:
            log.warning("bad cron for job %s (%r): %s", d.id, d.schedule, e)
            continue

        last = d.last_scheduled_at
        if last is None:
            d.last_scheduled_at = prev_fire  # baseline, don't fire retroactively
            db.session.commit()
            continue
        if prev_fire <= last:
            continue  # this slot already handled

        # New slot. Record it regardless so we don't backlog missed slots.
        d.last_scheduled_at = prev_fire
        active = db.session.scalar(
            db.select(JobRun)
            .filter_by(job_definition_id=d.id)
            .where(JobRun.status.in_(RUNNING_STATUSES))
            .limit(1)
        )
        if active:
            log.info("schedule skipped for job %s: a run is already active", d.id)
            db.session.commit()
            continue
        enqueue_batch(d)
        db.session.commit()
        fired += 1
        log.info("scheduled run enqueued for job %s (%r)", d.id, d.name)

    return f"fired {fired}"

# Placeholder run duration for the demo long_running_job task below.
SIMULATED_RUN_SECONDS = 30


@shared_task(bind=True)
def long_running_job(self, seconds: int = 10) -> str:
    """Simulate a long task (e.g. a browser script) that reports progress."""
    for elapsed in range(seconds):
        time.sleep(1)
        self.update_state(
            state="PROGRESS",
            meta={"elapsed": elapsed + 1, "total": seconds},
        )
    return f"done after {seconds}s"


@shared_task(bind=True)
def run_job_definition(self, definition_id: int, job_run_id: int) -> str:
    """Execute a job definition in an ephemeral sibling container (DooD).

    The launcher injects a per-run token + the runtime API base so the job's
    SDK can request inputs (e.g. MFA). Exit code 0 => SUCCESS. Cancellation
    stops the container via the kill endpoint; the JobRun is marked STOPPED
    there since a terminated worker can't update it itself.
    """
    from app.models import JobDefinition
    from app.runtime.launcher import DuplicateRun, launch_job, register_outputs

    run = db.session.get(JobRun, job_run_id)
    if run is None:
        return "missing job run"
    # Never re-run or clobber a run that already finished/stopped — e.g. if the
    # broker redelivers this task. (The launcher also refuses to disturb a live
    # container for an in-flight duplicate; see DuplicateRun below.)
    if run.status in ("SUCCESS", "FAILURE", "STOPPED"):
        log.warning("run %s already %s; ignoring duplicate dispatch",
                    job_run_id, run.status)
        return f"already {run.status}"
    definition = db.session.get(JobDefinition, definition_id)
    if definition is None:
        run.exit_code = EXIT_NO_DEFINITION
        run.status = "FAILURE"
        db.session.commit()
        return "missing job definition"

    # Decrypt parameters into a plain dict; the launcher passes them as PARAM_*.
    params = {p.key: p.value for p in definition.parameters}

    run.status = "STARTED"
    db.session.commit()
    try:
        exit_code, logs = launch_job(
            job_run_id, job_name=definition.script_path, params=params
        )
        log.info("run %s container logs:\n%s", job_run_id, logs)
        # Persist stdout (tail-capped to keep the row bounded) for the run page.
        run.stdout = logs[-1_000_000:] if logs else None
        # Register whatever the job produced, regardless of exit code.
        register_outputs(job_run_id)
        run.exit_code = exit_code
        run.status = "SUCCESS" if exit_code == EXIT_OK else "FAILURE"
        db.session.commit()
        if run.status == "FAILURE":
            _try_auto_resume(run, exit_code)
        return f"exit={exit_code}"
    except DuplicateRun as e:
        # Another execution owns this run (a redelivered task); leave its
        # status and output untouched.
        log.warning("duplicate dispatch for run %s: %s", job_run_id, e)
        return "duplicate"
    except Exception:
        # The worker/launcher raised before the job returned a code (e.g. a hung
        # portal action that got torn down). Record a sentinel so a terminal run
        # is never left with a NULL exit_code, then let auto-resume consider it.
        run.exit_code = EXIT_WORKER_ERROR
        run.status = "FAILURE"
        db.session.commit()
        _try_auto_resume(run, EXIT_WORKER_ERROR)
        raise


def _try_auto_resume(run, exit_code) -> None:
    """Best-effort auto-resume trigger: never let it mask the run's outcome."""
    from app.services import maybe_auto_resume
    try:
        maybe_auto_resume(run, exit_code)
    except Exception:
        log.warning("auto-resume check failed for run %s", run.id, exc_info=True)
        db.session.rollback()


@shared_task
def auto_resume_run(prior_run_id: int, attempt: int) -> str:
    """Fire (after a backoff) to auto-resume a failed run — unless a resume
    already exists or another run of the definition is active. This is what
    keeps a manual Resume (clicked before the timer elapses) from racing into a
    second, concurrent resume: by the time this runs, the manual resume's run is
    active / recorded, so we no-op."""
    from app.models.job_run import RUNNING_STATUSES
    from app.services import enqueue_resume

    prior = db.session.get(JobRun, prior_run_id)
    if prior is None:
        return "missing run"

    def _stop(reason):
        prior.auto_resume_at = None
        db.session.commit()
        log.info("auto-resume for run %s skipped: %s", prior_run_id, reason)
        return reason

    if prior.job_definition_id is None:
        return _stop("no definition")
    # A resume of this run already exists (e.g. the operator clicked Resume).
    already = db.session.scalar(
        db.select(JobRun).filter_by(resume_from_run_id=prior.id).limit(1))
    if already is not None:
        return _stop("already resumed")
    # Some run of this definition is currently active — don't add a concurrent one.
    active = db.session.scalar(
        db.select(JobRun)
        .filter_by(job_definition_id=prior.job_definition_id)
        .where(JobRun.status.in_(RUNNING_STATUSES))
        .limit(1))
    if active is not None:
        return _stop("another run active")
    # Defensive re-check of the cap (the definition may have changed).
    definition = prior.job_definition
    if prior.auto_resume_attempt >= (definition.auto_resume_max_attempts or 0):
        return _stop("attempt cap reached")

    enqueue_resume(prior, auto=True, attempt=attempt)  # also clears auto_resume_at
    log.info("auto-resumed run %s (attempt %d)", prior_run_id, attempt)
    return f"auto-resumed attempt {attempt}"
