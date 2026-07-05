"""Progress/log output. In the platform the job runs unattended in a container,
so everything is plain stdout (captured by the launcher) — no prompts, no MFA
logic (that's the runtime input channel now).
"""


def banner():
    print("=== Prime Therapeutics eInvoice scraper ===", flush=True)


def info(msg):
    print(f"  {msg}", flush=True)


def step(msg):
    print(f"> {msg}", flush=True)


def success(msg):
    print(f"  {msg}", flush=True)


def warn(msg):
    print(f"  WARNING: {msg}", flush=True)


def error(msg):
    print(f"  ERROR: {msg}", flush=True)


def progress(combo, report_label, idx, total, invoice_no, status):
    print(f"  {combo.business_line} / {combo.program} / {report_label}"
          f" - {idx}/{total} {invoice_no} ... {status}", flush=True)


def summary(counts, output_dir):
    print(f"""
================= RUN SUMMARY =================
  Downloaded:        {counts.get('DOWNLOADED', 0)}
  Skipped (already): {counts.get('SKIPPED_EXISTS', 0)}
  No invoice data:   {counts.get('NO_DATA', 0)}
  Would download:    {counts.get('WOULD_DOWNLOAD', 0)}
  Empty combos:      {counts.get('EMPTY_COMBO', 0)}
  FAILED:            {counts.get('FAILED', 0)}
  Output dir:        {output_dir}
================================================
""", flush=True)
