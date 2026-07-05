#!/usr/bin/env bash
# Run the job headed on a virtual display, and mirror that display over VNC so
# the platform can stream it live to an operator (who can also take over).
set -euo pipefail

SCREEN="${DATAPULL_SCREEN:-1280x1024x24}"
Xvfb :99 -screen 0 "$SCREEN" -nolisten tcp &
export DISPLAY=:99

# Wait for the display to come up.
for _ in $(seq 1 50); do
  xdpyinfo -display :99 >/dev/null 2>&1 && break
  sleep 0.1
done

# Live view (best effort — never block the job if VNC can't start). Bound to
# the container's internal :5900; the platform reaches it by container name on
# the Docker network and proxies it to the browser over an authenticated WS.
x11vnc -display :99 -rfbport 5900 -forever -shared -nopw -quiet -bg \
  -o /tmp/x11vnc.log || echo "x11vnc failed to start (no live view)"

exec python -u /opt/datapull/run.py
