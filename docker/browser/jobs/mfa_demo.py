"""Demo job: exercises the runtime input channel end-to-end from inside a
launched container — no browser involved. Requests an MFA code via the SDK
(resolved by the mailbox provider or an operator) and prints it.
"""
from datapull_runtime import request_input


def main() -> int:
    print("mfa_demo: requesting an MFA code via the runtime API ...", flush=True)
    code = request_input(
        "okta_mfa",
        kind="otp",
        prompt="Enter the Okta email verification code",
        timeout=180,
        poll=3,
    )
    print(f"mfa_demo: received code of length {len(code)} — proceeding.", flush=True)
    return 0
