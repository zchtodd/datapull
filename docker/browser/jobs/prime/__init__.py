"""Prime Therapeutics eInvoice scraper, ported to the datapull platform.

Config comes from PARAM_* env vars (job parameters), MFA comes from the runtime
input channel (resolved by the bound graph_mailbox connection or an operator),
and downloads land under DATAPULL_OUTPUT_DIR (the shared outputs volume), which
the platform registers as run outputs.

The dispatcher imports this package and calls main().
"""
from jobs.prime.entry import main

__all__ = ["main"]
