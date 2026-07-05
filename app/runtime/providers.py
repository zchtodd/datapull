"""Automated providers that resolve a JobInputRequest without a human.

Currently: GraphMailboxOtpProvider — fetches Okta-style 6-digit verification
codes from a mailbox via the Microsoft Graph API (client-credentials flow).
Lifted from the standalone script's mailmfa.py, but reads its credentials from
a platform Connection's config dict instead of a bundled settings file.

Stdlib only (urllib) so it carries no extra dependency.
"""
import json
import logging
import re
import urllib.parse
import urllib.request

log = logging.getLogger("datapull.runtime")

GRAPH = "https://graph.microsoft.com/v1.0"
# A standalone 6-digit number — Okta verification codes.
CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
TAG_RE = re.compile(r"<[^>]+>")


class ProviderError(Exception):
    pass


def _post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _get_json(url, token):
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


class GraphMailboxOtpProvider:
    """Polls a mailbox for the newest Okta verification code.

    Config keys (from a `graph_mailbox` Connection): tenant_id, client_id,
    client_secret, mailbox, and optional from_contains (default "okta.com").
    """

    kind = "otp"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._token = None

    def ready(self) -> bool:
        return all(
            self.cfg.get(k)
            for k in ("tenant_id", "client_id", "client_secret", "mailbox")
        )

    def _get_token(self) -> str:
        if self._token:
            return self._token
        url = (
            f"https://login.microsoftonline.com/{self.cfg['tenant_id']}"
            "/oauth2/v2.0/token"
        )
        try:
            data = _post_form(
                url,
                {
                    "grant_type": "client_credentials",
                    "client_id": self.cfg["client_id"],
                    "client_secret": self.cfg["client_secret"],
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
        except urllib.error.HTTPError as e:
            raise ProviderError(
                f"token request failed: HTTP {e.code}: "
                f"{e.read().decode(errors='replace')[:300]}"
            ) from e
        self._token = data["access_token"]
        return self._token

    def _recent_messages(self, since_utc):
        token = self._get_token()
        mailbox = urllib.parse.quote(self.cfg["mailbox"])
        since = since_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        params = urllib.parse.urlencode(
            {
                "$filter": f"receivedDateTime ge {since}",
                "$orderby": "receivedDateTime desc",
                "$top": "10",
                "$select": "from,subject,bodyPreview,body,receivedDateTime",
            }
        )
        try:
            data = _get_json(f"{GRAPH}/users/{mailbox}/messages?{params}", token)
        except urllib.error.HTTPError as e:
            raise ProviderError(
                f"Graph mail query failed: HTTP {e.code}: "
                f"{e.read().decode(errors='replace')[:300]}"
            ) from e
        return data.get("value", [])

    def _looks_relevant(self, msg) -> bool:
        sender = (((msg.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
        subject = (msg.get("subject") or "").lower()
        needle = (self.cfg.get("from_contains") or "okta.com").lower()
        return (
            needle in sender
            or "okta" in subject
            or "okta" in (msg.get("bodyPreview") or "").lower()
        )

    @staticmethod
    def _extract_code(msg):
        for text in (
            msg.get("subject") or "",
            TAG_RE.sub(" ", ((msg.get("body") or {}).get("content") or "")),
        ):
            m = CODE_RE.search(text)
            if m:
                return m.group(1)
        return None

    def fetch_since(self, since_utc) -> str | None:
        """One poll: newest matching code received after since_utc, or None."""
        for msg in self._recent_messages(since_utc):
            if not self._looks_relevant(msg):
                continue
            code = self._extract_code(msg)
            if code:
                log.info(
                    "mailbox OTP found in %r received %s",
                    msg.get("subject"), msg.get("receivedDateTime"),
                )
                return code
        return None
