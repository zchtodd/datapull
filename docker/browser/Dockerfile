# Dedicated browser executor image: Chromium + Playwright + Xvfb + the SDK.
# Built from the repo root:  docker build -f docker/browser/Dockerfile -t datapull-browser .
FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

# DEBIAN_FRONTEND=noninteractive so tzdata (pulled in transitively) doesn't
# block on its interactive timezone prompt.
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        xvfb x11-utils \
    && rm -rf /var/lib/apt/lists/*

# The Playwright browsers ship in the base at /ms-playwright; install the
# matching pip package (no browser download — PLAYWRIGHT_BROWSERS_PATH is set).
RUN pip install --no-cache-dir playwright==1.52.0

WORKDIR /opt/datapull

# The runtime SDK (stdlib-only) and the job dispatcher/jobs.
COPY sdk/datapull_runtime.py /opt/datapull/datapull_runtime.py
COPY docker/browser/run.py /opt/datapull/run.py
COPY docker/browser/jobs /opt/datapull/jobs
COPY docker/browser/entrypoint.sh /opt/datapull/entrypoint.sh
RUN chmod +x /opt/datapull/entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/datapull

ENTRYPOINT ["/opt/datapull/entrypoint.sh"]
