"""Container entrypoint: dispatch to the job named by DATAPULL_JOB.

Job modules live in jobs/ and expose main() -> int (process exit code).
"""
import importlib
import os
import sys


def main() -> int:
    job = os.environ.get("DATAPULL_JOB", "").strip()
    if not job:
        print("DATAPULL_JOB is not set", file=sys.stderr)
        return 2
    try:
        mod = importlib.import_module(f"jobs.{job}")
    except ModuleNotFoundError as e:
        print(f"unknown job {job!r}: {e}", file=sys.stderr)
        return 2
    return int(mod.main())


if __name__ == "__main__":
    sys.exit(main())
