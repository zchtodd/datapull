r"""Seed/refresh the Prime eInvoices job's non-secret parameters from a JSON
snapshot (scripts/prime_params.json), so a fresh or incomplete deployment gets
the same LOGIN_URL / PROGRAMS / SKIP_OPTION_LABELS as the working environment.

Meant for the Windows VM, where the easiest way to move data in is `git pull`:
pull, then run this. It's an idempotent upsert keyed on (job_definition_id,
key) — safe to run repeatedly; it updates existing params and adds missing
ones, and never touches secrets (the snapshot contains none).

Run inside the web container:

    docker compose exec web python /app/scripts/seed_prime_params.py

Or natively on the VM (from the repo root, with .env loaded — see DEPLOY.md):

    .\.venv\Scripts\python.exe scripts\seed_prime_params.py
"""
import json
import os
import sys

# Ensure the repo root is importable regardless of how the script is invoked.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import JobDefinition, JobParameter  # noqa: E402

SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prime_params.json")


def seed() -> int:
    with open(SNAPSHOT, encoding="utf-8") as fh:
        doc = json.load(fh)

    script_path = doc["script_path"]
    jd = JobDefinition.query.filter_by(script_path=script_path).first()
    if jd is None:
        print(f"ERROR: no job definition with script_path={script_path!r}. "
              f"Create the '{doc['name']}' job first, then re-run.")
        return 1

    existing = {p.key: p for p in jd.parameters}
    added, updated, unchanged = 0, 0, 0
    for spec in doc["parameters"]:
        if spec["is_secret"]:
            # The snapshot is non-secret by design; never seed secrets this way.
            print(f"  skip {spec['key']}: marked secret, not seeding")
            continue
        param = existing.get(spec["key"])
        if param is None:
            param = JobParameter(job_definition_id=jd.id, key=spec["key"])
            param.is_secret = False
            param.value_type = spec["value_type"]
            param.value = spec["value"]
            db.session.add(param)
            added += 1
            print(f"  add    {spec['key']}")
        elif param.value != spec["value"] or param.value_type != spec["value_type"]:
            param.value_type = spec["value_type"]
            param.value = spec["value"]
            updated += 1
            print(f"  update {spec['key']}")
        else:
            unchanged += 1
            print(f"  ok     {spec['key']} (unchanged)")

    db.session.commit()
    print(f"Done: {added} added, {updated} updated, {unchanged} unchanged "
          f"on job '{jd.name}' (id={jd.id}).")
    return 0


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        sys.exit(seed())
