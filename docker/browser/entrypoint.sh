#!/usr/bin/env bash
# Run the job on a virtual display so headed Chromium has somewhere to render.
# The live view is no longer VNC — the job writes periodic screenshots that the
# web serves (see DATAPULL_LIVE_FRAME), which works the same headed or headless
# and on both Linux/Docker and native Windows.
set -euo pipefail

SCREEN="${DATAPULL_SCREEN:-1280x1024x24}"
Xvfb :99 -screen 0 "$SCREEN" -nolisten tcp &
export DISPLAY=:99

# Wait for the display to come up.
for _ in $(seq 1 50); do
  xdpyinfo -display :99 >/dev/null 2>&1 && break
  sleep 0.1
done

exec python -u /opt/datapull/run.py
