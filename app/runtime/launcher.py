"""Run a job as an ephemeral sibling container (Docker-out-of-Docker).

The worker reaches the Docker daemon through the socket proxy (DOCKER_HOST), so
it never touches the raw host socket. Each job runs in a fresh container from
the browser image, joined to the app network, with a per-run token + the runtime
API base injected so the job's SDK can request inputs (e.g. MFA). The container
is removed when done; cancellation stops it.
"""
import csv
import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import time

from sqlalchemy import text

from app.extensions import db
from app.models import JobRun, JobRunConnection, JobRunOutput
from app.runtime.auth import issue_run_token

log = logging.getLogger("datapull.runtime")

RUN_LABEL = "datapull.run_id"
# Shared outputs volume (mounted in the worker and the launched container) and
# the per-run subdirectory jobs write into.
OUTPUTS_DIR = os.environ.get("OUTPUTS_DIR", "/data/outputs")
OUTPUTS_VOLUME = os.environ.get("DATAPULL_OUTPUTS_VOLUME", "datapull_outputs")
# Hard cap on a run container's lifetime. Generous by default: a long scrape
# plus a multi-hour wait for an operator to supply a mid-run MFA code must not
# be killed prematurely. The heartbeat log + live view let operators notice a
# genuinely stuck run and Stop it manually. Override with DATAPULL_RUN_TIMEOUT_S.
RUN_TIMEOUT_S = int(os.environ.get("DATAPULL_RUN_TIMEOUT_S", str(24 * 3600)))
# How often (seconds) launch_job re-scans a running job's output dir to register
# newly-downloaded files, so progress survives a mid-run failure.
REGISTER_EVERY_S = 15

# Runtime mode: "docker" launches each job as an ephemeral sibling container
# (dev / Linux hosts); "native" runs it as a local Playwright subprocess in the
# same venv (Windows VM without Docker — headed Chromium on the RDP desktop).
LAUNCHER = os.environ.get("DATAPULL_LAUNCHER", "docker").strip().lower()
# Native mode: where the browser job code (run.py + jobs/) and the SDK live, and
# where per-run console logs + PID files are written (so the web process can
# find and stop a run the worker started).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JOBS_DIR = os.environ.get("DATAPULL_JOBS_DIR", os.path.join(_REPO_ROOT, "docker", "browser"))
SDK_DIR = os.environ.get("DATAPULL_SDK_DIR", os.path.join(_REPO_ROOT, "sdk"))
RUNTIME_DIR = os.environ.get("DATAPULL_RUNTIME_DIR", os.path.join(OUTPUTS_DIR, ".runtime"))


def container_name(job_run_id) -> str:
    return f"datapull-run-{job_run_id}"


def run_output_dir(job_run_id) -> str:
    return os.path.join(OUTPUTS_DIR, f"run_{job_run_id}")


def live_frame_path(job_run_id) -> str:
    """Where the job writes its latest live-view screenshot and the web serves it
    from. Under OUTPUTS_DIR (shared with the job in both Docker and native), but
    in a sibling `.live/` dir — NOT the run's output dir — so register_outputs
    never mistakes it for a deliverable."""
    return os.path.join(OUTPUTS_DIR, ".live", f"run_{job_run_id}.jpg")


# Files written at the run-dir root are diagnostics, not deliverables — never
# seed them into a resume run.
_SEED_SKIP_NAMES = frozenset({"run.log", "manifest.csv", "manifest.json"})


def _seed_from_prior(prior_run_id, out_dir) -> int:
    """Hard-link a prior run's deliverable files into out_dir so the job's
    existing-file check skips already-completed work. Hard links share inodes
    (near-free on the same volume, and they survive deletion of the prior dir);
    falls back to a copy across devices. Skips the scratch dir and diagnostics.
    Returns the number of files seeded."""
    prior = run_output_dir(prior_run_id)
    if not os.path.isdir(prior):
        log.warning("resume: prior run dir %s is missing; nothing to seed", prior)
        return 0
    count = 0
    for root, dirs, files in os.walk(prior):
        if root == prior:
            dirs[:] = [d for d in dirs if d != "tmp"]
        for name in files:
            if name in _SEED_SKIP_NAMES or name.startswith("fail_"):
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(src, prior)
            dst = os.path.join(out_dir, rel)
            if os.path.exists(dst):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                os.link(src, dst)
            except OSError:
                try:
                    shutil.copy2(src, dst)
                except OSError as e:
                    log.warning("resume: could not seed %s: %s", rel, e)
                    continue
            count += 1
    return count


def _prior_quarter(prior_run_id):
    """The quarter (YYYYQ) the prior run used, so a resume targets the same
    data. Prefer the manifest's year_qtr column; else parse it back out of a
    top-level output folder name like 'AK 2026-1Q'. Returns None if unknown."""
    base = run_output_dir(prior_run_id)
    manifest = os.path.join(base, "manifest.csv")
    try:
        with open(manifest, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                q = (row.get("year_qtr") or "").strip()
                if len(q) == 5 and q.isdigit():
                    return q
    except (OSError, csv.Error):
        pass
    try:
        for name in sorted(os.listdir(base)):
            m = re.search(r"\b(\d{4})-(\d)Q\b", name)
            if m:
                return f"{m.group(1)}{m.group(2)}"
    except OSError:
        pass
    return None


def _valid_quarter(q):
    """A YYYYQ quarter string (e.g. '20261'), or None."""
    q = (q or "").strip() if isinstance(q, str) else ""
    return q if (len(q) == 5 and q.isdigit() and q[4] in "1234") else None


def _seed_from_quarter(definition_id, quarter, out_dir, exclude_run_id) -> int:
    """Hard-link files this job definition already downloaded for `quarter`, from
    ALL prior runs, into out_dir — so a fresh start of an already-run quarter
    shows those files (as 'seen before'), even for programs skipped by a
    checkpoint. Prime-specific: quarter files live under top-level folders named
    like 'AK 2026-1Q', so `2026-1Q` identifies them. Returns files seeded."""
    token = f"{quarter[:4]}-{quarter[4]}Q"  # 20261 -> 2026-1Q
    prior_ids = db.session.scalars(
        db.select(JobRun.id).filter(
            JobRun.job_definition_id == definition_id,
            JobRun.id != exclude_run_id,
        ).order_by(JobRun.id)
    ).all()
    count = 0
    for pid in prior_ids:
        base = run_output_dir(pid)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if root == base:
                dirs[:] = [d for d in dirs if d != "tmp"]
            rel = os.path.relpath(root, base)
            if token not in rel:  # only this quarter's folders
                continue
            for name in files:
                if name in _SEED_SKIP_NAMES or name.startswith("fail_"):
                    continue
                src = os.path.join(root, name)
                dst = os.path.join(out_dir, os.path.relpath(src, base))
                if os.path.exists(dst):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    os.link(src, dst)
                except OSError:
                    try:
                        shutil.copy2(src, dst)
                    except OSError:
                        continue
                count += 1
    return count


def register_outputs(job_run_id) -> int:
    """Register files the job left under its output dir as JobRunOutput rows
    (served later by the download endpoint). Returns the count of newly added
    rows. Idempotent: files already recorded for the run are skipped, so this
    is safe to call from both the normal task path and the stop/kill path."""
    base = run_output_dir(job_run_id)
    if not os.path.isdir(base):
        return 0
    # Serialize registration for this run across processes. The worker's
    # incremental/end-of-run passes and the web stop-path each call this with
    # their own DB session; without coordination they can both read `already`
    # before either commits and then double-insert every file (a check-then-
    # insert race — exactly what produced duplicate rows when a run was stopped
    # mid-scan). An exclusive, transaction-scoped MSSQL app lock — released
    # automatically when this function commits/rolls back — makes concurrent
    # callers take turns, so the dedup below actually holds.
    try:
        if db.session.get_bind().dialect.name == "mssql":
            db.session.execute(
                text("EXEC sp_getapplock @Resource=:r, @LockMode='Exclusive', "
                     "@LockOwner='Transaction', @LockTimeout=20000"),
                {"r": f"reg_outputs_{job_run_id}"})
    except Exception as e:
        log.debug("register_outputs lock skipped (%s); proceeding best-effort", e)
    run = db.session.get(JobRun, job_run_id)
    definition_id = run.job_definition_id if run else None
    already = set(db.session.scalars(
        db.select(JobRunOutput.storage_path).filter_by(job_run_id=job_run_id)
    ).all())
    count = 0
    for root, dirs, files in os.walk(base):
        if root == base:
            # Skip the job's scratch dir: files there are mid-download and get
            # moved to their final path (or cleaned up). Registering them would
            # create rows pointing at transient paths — matters once we scan
            # incrementally, while the run (and tmp/) is still live.
            dirs[:] = [d for d in dirs if d != "tmp"]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, OUTPUTS_DIR)
            if rel in already:
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = None
            content_hash = _sha256(full)
            db.session.add(JobRunOutput(
                job_run_id=job_run_id, filename=name, storage_path=rel,
                size_bytes=size, content_hash=content_hash,
                is_new=_is_new_content(content_hash, job_run_id, definition_id),
            ))
            count += 1
    db.session.commit()
    log.info("registered %d output(s) for run %s", count, job_run_id)
    return count


def _sha256(path):
    """SHA-256 hex of a file's content, or None if it can't be read."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _is_new_content(content_hash, job_run_id, definition_id):
    """True if this content was new at registration time — no *other* run (of
    the same job definition) already produced a file with the same hash. None if
    the hash is unknown."""
    if content_hash is None:
        return None
    q = (db.select(JobRunOutput.id)
         .join(JobRun, JobRunOutput.job_run_id == JobRun.id)
         .where(JobRunOutput.content_hash == content_hash,
                JobRunOutput.job_run_id != job_run_id))
    if definition_id is not None:
        q = q.where(JobRun.job_definition_id == definition_id)
    return db.session.scalar(q.limit(1)) is None


class LaunchError(Exception):
    pass


class DuplicateRun(Exception):
    """A live container for this run already exists — another execution (e.g. a
    broker redelivery of the same task) owns it. Abort without disturbing it."""


def _client():
    # Reads DOCKER_HOST (the socket proxy) from the environment. Imported lazily
    # so native (non-Docker) hosts don't need the docker package installed.
    import docker
    return docker.from_env()


def launch_job(
    job_run_id,
    job_name,
    params=None,
    timeout_s=RUN_TIMEOUT_S,
    poll_s=2,
    mem_limit="2g",
):
    """Run a job to completion in a sibling container. Returns (exit_code, logs).

    Stops the container if it exceeds timeout_s. Removes it either way.
    """
    run = db.session.get(JobRun, job_run_id)
    if run is None:
        raise LaunchError(f"no such job run {job_run_id}")

    # Ensure the run has its connection snapshot (job_start records it from
    # defaults + overrides; this is a fallback for other dispatch paths).
    if not run.connections and run.job_definition is not None:
        for b in run.job_definition.connection_bindings:
            db.session.add(JobRunConnection(
                job_run_id=run.id, connection_id=b.connection_id))
        db.session.commit()

    # Merge params from attached non-MFA connections into the job's params; the
    # definition's own params win on key collisions. MFA connections are
    # consumed server-side by the OTP provider and never injected.
    params = dict(params or {})
    for jrc in run.connections:
        if jrc.connection.is_mfa:
            continue
        for p in jrc.connection.parameters:
            params.setdefault(p.key, p.value)

    # Issue the per-run token now and hand the plaintext to the container.
    token = issue_run_token(run)
    db.session.commit()

    image = os.environ.get("DATAPULL_BROWSER_IMAGE", "datapull-browser")
    network = os.environ.get("DATAPULL_NETWORK")
    api_base = os.environ.get("DATAPULL_API_BASE") or (
        "http://localhost:5000/api" if LAUNCHER == "native"
        else "http://web:5000/api")

    out_dir = run_output_dir(job_run_id)
    os.makedirs(out_dir, exist_ok=True)

    # Resume: seed this run's output dir from the run it continues (so the job's
    # existing-file check skips already-downloaded invoices) and pin the same
    # quarter (so the seeded files line up with the new run's target paths).
    if run.resume_from_run_id:
        seeded = _seed_from_prior(run.resume_from_run_id, out_dir)
        quarter = _prior_quarter(run.resume_from_run_id)
        if quarter:
            params["QUARTER"] = quarter  # force: resume must target the same quarter
        log.info("resume run %s: seeded %d file(s) from run %s, quarter=%s",
                 job_run_id, seeded, run.resume_from_run_id, quarter or "(unknown)")
    elif run.job_definition_id and not run.from_scratch:
        # Fresh start of a quarter this job already ran: seed the prior files so
        # they show as 'seen before' (and aren't re-downloaded), even where a
        # checkpoint skips the program. Needs the quarter known at launch — i.e.
        # set as a QUARTER parameter (a prompted-only quarter isn't known yet).
        # Skipped for a from-scratch run, which re-downloads everything.
        q = _valid_quarter(params.get("QUARTER"))
        if q:
            seeded = _seed_from_quarter(run.job_definition_id, q, out_dir, job_run_id)
            if seeded:
                log.info("run %s: seeded %d prior file(s) for quarter %s "
                         "(shown as 'seen before')", job_run_id, seeded, q)

    # Live view: the job writes periodic screenshots here; the web serves them.
    live_frame = live_frame_path(job_run_id)
    os.makedirs(os.path.dirname(live_frame), exist_ok=True)

    env = {
        "DATAPULL_API_BASE": api_base,
        "DATAPULL_RUN_TOKEN": token,
        "DATAPULL_JOB": job_name,
        "DATAPULL_OUTPUT_DIR": out_dir,
        "DATAPULL_LIVE_FRAME": live_frame,
    }
    # For fan-out runs, tell the job which client it's running as (so it can
    # label/foldername its outputs).
    if run.client_label:
        env["PARAM_CLIENT"] = run.client_label
    # Job parameters arrive as PARAM_<KEY> env vars (secrets decrypted upstream).
    for key, value in (params or {}).items():
        if value is not None:
            env[f"PARAM_{key}"] = str(value)

    if LAUNCHER == "native":
        return _launch_native(job_run_id, job_name, env, timeout_s, poll_s)
    return _launch_docker(job_run_id, job_name, env, image, network,
                          timeout_s, poll_s, mem_limit)


def stop_job(job_run_id) -> bool:
    """Stop a run's process/container (used by cancellation). Best effort."""
    if LAUNCHER == "native":
        return _stop_native(job_run_id)
    return _stop_docker(job_run_id)


# --------------------------------------------------------- native subprocess
# Windows/no-Docker: run the job as a local Playwright subprocess in this venv.
# A per-run PID file under RUNTIME_DIR lets the web stop-path kill a run the
# worker started. Console output is captured to RUNTIME_DIR (outside the run's
# output dir, so it isn't registered as a deliverable).

def _read_pid(path):
    try:
        with open(path) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


def _kill_tree(pid):
    """Terminate a process and all its descendants (Chromium spawns children)."""
    try:
        import psutil
    except Exception:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True)
            else:
                os.kill(pid, 15)  # SIGTERM
        except Exception:
            pass
        return
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    procs = parent.children(recursive=True) + [parent]
    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=8)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass


def _launch_native(job_run_id, job_name, env, timeout_s, poll_s):
    """Run the job as `python run.py` using the venv's Playwright (headed on the
    interactive desktop). Returns (exit_code, logs); enforces timeout_s."""
    try:
        import psutil
        pid_alive = psutil.pid_exists
    except Exception:
        pid_alive = lambda p: False  # noqa: E731 (best-effort without psutil)

    os.makedirs(RUNTIME_DIR, exist_ok=True)
    pid_path = os.path.join(RUNTIME_DIR, f"run_{job_run_id}.pid")
    log_path = os.path.join(RUNTIME_DIR, f"run_{job_run_id}.console.log")

    existing = _read_pid(pid_path)
    if existing and pid_alive(existing):
        raise DuplicateRun(
            f"run {job_run_id} already has a live process (pid {existing}); "
            "refusing to start a duplicate")

    # Inherit the OS environment (PATH etc. so Chromium launches) + our vars,
    # and put the job code + SDK on PYTHONPATH so `run.py` can import them.
    proc_env = dict(os.environ)
    proc_env.update(env)
    existing_pp = [proc_env["PYTHONPATH"]] if proc_env.get("PYTHONPATH") else []
    proc_env["PYTHONPATH"] = os.pathsep.join([JOBS_DIR, SDK_DIR] + existing_pp)
    proc_env.setdefault("PYTHONUNBUFFERED", "1")

    log.info("launching native job process job=%s run=%s (cwd=%s)",
             job_name, job_run_id, JOBS_DIR)
    logf = open(log_path, "w", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen([sys.executable, "-u", "run.py"],
                                cwd=JOBS_DIR, env=proc_env,
                                stdout=logf, stderr=subprocess.STDOUT)
    except Exception as e:
        logf.close()
        raise LaunchError(f"could not start native job process: {e}")
    with open(pid_path, "w") as fh:
        fh.write(str(proc.pid))

    try:
        deadline = time.monotonic() + timeout_s
        last_reg = 0.0
        while proc.poll() is None:
            if time.monotonic() > deadline:
                log.warning("run %s exceeded %ss; killing process tree",
                            job_run_id, timeout_s)
                _kill_tree(proc.pid)
                break
            now = time.monotonic()
            if now - last_reg >= REGISTER_EVERY_S:
                last_reg = now
                try:
                    register_outputs(job_run_id)
                except Exception:
                    log.warning("incremental register_outputs failed for run %s",
                                job_run_id, exc_info=True)
                    db.session.rollback()
            time.sleep(poll_s)
        exit_code = proc.wait()
    finally:
        try:
            logf.close()
        except Exception:
            pass
        try:
            os.remove(pid_path)
        except OSError:
            pass

    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            logs = fh.read()[-1_000_000:]
    except OSError:
        logs = ""
    return exit_code, logs


def _stop_native(job_run_id) -> bool:
    pid = _read_pid(os.path.join(RUNTIME_DIR, f"run_{job_run_id}.pid"))
    if not pid:
        return False
    log.info("stopping native process for run %s (pid %s)", job_run_id, pid)
    _kill_tree(pid)
    return True


# --------------------------------------------------------- docker container
def _launch_docker(job_run_id, job_name, env, image, network,
                   timeout_s, poll_s, mem_limit):
    """Run the job to completion in an ephemeral sibling container."""
    import docker
    client = _client()
    # Deterministic name so the platform can reach the container's VNC port by
    # DNS (datapull-run-<id>) on the shared network for the live-view proxy.
    name = container_name(job_run_id)
    # If a container for this run already exists, decide carefully: a LIVE one
    # means another execution owns this run (a duplicate/redelivered task) — do
    # NOT kill it. Only clear a stale, already-exited leftover before relaunching.
    try:
        existing = client.containers.get(name)
    except docker.errors.NotFound:
        existing = None
    except Exception:
        existing = None
    if existing is not None:
        if existing.status in ("running", "created", "restarting", "paused"):
            raise DuplicateRun(
                f"run {job_run_id} already has a live container ({existing.status}); "
                "refusing to start a duplicate")
        try:
            existing.remove(force=True)
        except Exception:
            pass
    log.info("launching container %s image=%s job=%s run=%s", name, image, job_name, job_run_id)
    container = client.containers.run(
        image,
        name=name,
        detach=True,
        init=True,  # tini as PID 1 reaps the Xvfb child (else it hangs)
        environment=env,
        network=network,
        shm_size="1g",  # Chromium needs more than the default 64MB /dev/shm
        mem_limit=mem_limit,
        # Share the outputs volume so files the job writes survive the container.
        volumes={OUTPUTS_VOLUME: {"bind": OUTPUTS_DIR, "mode": "rw"}},
        labels={RUN_LABEL: str(job_run_id), "datapull.job": str(job_name)},
    )

    try:
        deadline = time.monotonic() + timeout_s
        last_reg = 0.0
        while time.monotonic() < deadline:
            try:
                container.reload()
            except docker.errors.NotFound:
                # Stopped+removed out from under us (e.g. a kill). Not an error.
                log.info("container for run %s is gone; treating as ended", job_run_id)
                return -1, "(container was removed)"
            if container.status == "exited":
                break
            # Register files as they're downloaded so a long run that later
            # crashes/stops/times out still leaves the user with everything
            # captured so far, rather than nothing. Idempotent + failure-isolated.
            now = time.monotonic()
            if now - last_reg >= REGISTER_EVERY_S:
                last_reg = now
                try:
                    register_outputs(job_run_id)
                except Exception:
                    log.warning("incremental register_outputs failed for run %s",
                                job_run_id, exc_info=True)
                    db.session.rollback()
            time.sleep(poll_s)
        else:
            log.warning("run %s exceeded %ss; stopping container", job_run_id, timeout_s)
            try:
                container.stop(timeout=10)
                container.reload()
            except Exception as e:
                log.warning("stop after timeout failed: %s", e)

        try:
            exit_code = container.attrs.get("State", {}).get("ExitCode", -1)
            logs = container.logs().decode(errors="replace")
        except docker.errors.NotFound:
            return -1, "(container was removed)"
        return exit_code, logs
    finally:
        try:
            container.remove(force=True)
        except Exception as e:
            log.debug("container remove (already gone?): %s", e)


def _stop_docker(job_run_id) -> bool:
    try:
        client = _client()
        for c in client.containers.list(
            all=True, filters={"label": f"{RUN_LABEL}={job_run_id}"}
        ):
            log.info("stopping container %s for run %s", c.short_id, job_run_id)
            try:
                c.stop(timeout=10)
            except Exception as e:
                log.warning("stop failed: %s", e)
            return True
    except Exception as e:
        log.warning("stop_job failed: %s", e)
    return False
