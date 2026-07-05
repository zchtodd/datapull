"""Standalone check for the email-MFA mailbox provider.

Exercises the exact path the runtime auto-resolver uses: it loads the is_mfa
Connection from the DB, decrypts its params, builds the GraphMailboxOtpProvider,
acquires an Entra token, and queries the mailbox — so a green run here means a
real MFA request would resolve too. No job/browser/run involved.

Run inside the web container (it has the app code, DB access, and the
decryption key):

    docker compose exec web python /app/scripts/check_mfa_mailbox.py
    # optionally target one connection by name:
    docker compose exec web python /app/scripts/check_mfa_mailbox.py "Prime Okta MFA mailbox"
"""
import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure the repo root (this file's parent's parent) is importable, regardless
# of how the script is invoked — Python otherwise puts only scripts/ on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db
from app.models import Connection
from app.runtime.providers import GraphMailboxOtpProvider, ProviderError
from app.services import connection_config

REQUIRED = ("tenant_id", "client_id", "client_secret", "mailbox")


def _mask(v: str) -> str:
    if not v:
        return "(empty)"
    return f"(set, {len(v)} chars, ends …{v[-4:]})"


def check(name: str | None) -> int:
    q = db.select(Connection).filter_by(is_mfa=True)
    if name:
        q = q.filter_by(name=name)
    conns = db.session.scalars(q.order_by(Connection.name)).all()
    if not conns:
        print("No is_mfa connection found"
              + (f" named {name!r}." if name else "."))
        return 2
    if len(conns) > 1 and not name:
        print(f"Multiple MFA connections; checking all {len(conns)}.\n")

    worst = 0
    for conn in conns:
        print(f"=== Connection: {conn.name!r} (id={conn.id}) ===")
        cfg = connection_config(conn)
        for k in REQUIRED:
            print(f"  {k:14} {_mask(cfg.get(k))}")
        print(f"  {'from_contains':14} {cfg.get('from_contains') or '(default: okta.com)'}")

        provider = GraphMailboxOtpProvider(cfg)
        if not provider.ready():
            missing = [k for k in REQUIRED if not cfg.get(k)]
            print(f"  RESULT: NOT READY — missing {missing}\n")
            worst = max(worst, 2)
            continue

        # 1) Token (Entra). Catches bad secret / wrong tenant or client id.
        try:
            provider._get_token()
            print("  token:          OK (Entra issued an app token)")
        except ProviderError as e:
            print(f"  token:          FAILED\n    {e}\n")
            worst = max(worst, 1)
            continue

        # 2) Mailbox read (Graph). Catches missing Mail.Read consent / access
        #    policy / wrong mailbox address.
        since = datetime.now(timezone.utc) - timedelta(days=1)
        try:
            msgs = provider._recent_messages(since)
            print(f"  mailbox read:   OK ({len(msgs)} message(s) in the last 24h)")
        except ProviderError as e:
            print(f"  mailbox read:   FAILED\n    {e}\n")
            worst = max(worst, 1)
            continue

        # 3) Would we have found a code? (informational — depends on inbox.)
        relevant = [m for m in msgs if provider._looks_relevant(m)]
        code = provider.fetch_since(since)
        print(f"  matching mail:  {len(relevant)} of {len(msgs)} look relevant "
              f"(filter: from/subject/body contains the from_contains needle)")
        print(f"  code extracted: {'yes' if code else 'no'}"
              + (" — auto-retrieval is fully working" if code
                 else " — auth+access OK; no recent code in the inbox to extract"))
        print("  RESULT: OK\n")

    return worst


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else None
    app = create_app()
    with app.app_context():
        return check(name)


if __name__ == "__main__":
    sys.exit(main())
