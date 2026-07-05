"""Live browser view: bridge an operator's WebSocket to the run container's
x11vnc TCP port. noVNC in the browser speaks RFB-over-WebSocket; we relay the
raw bytes to <container>:5900 (reachable by the deterministic container name on
the shared Docker network). Login-gated; the operator can take over input from
the noVNC client side.
"""
import logging
import socket
import threading

from flask_login import current_user

from app.extensions import db
from app.models import JobRun
from app.runtime.launcher import container_name

log = logging.getLogger("datapull.live")

VNC_PORT = 5900


def register_live(sock):
    @sock.route("/ws/runs/<int:run_id>/vnc")
    def vnc(ws, run_id):
        if not current_user.is_authenticated:
            return
        run = db.session.get(JobRun, run_id)
        if run is None or not run.is_running:
            return

        host = container_name(run_id)
        try:
            upstream = socket.create_connection((host, VNC_PORT), timeout=10)
        except OSError as e:
            log.warning("live view: cannot reach %s:%s for run %s: %s",
                        host, VNC_PORT, run_id, e)
            return

        stop = threading.Event()

        def pump_upstream_to_client():
            try:
                while not stop.is_set():
                    data = upstream.recv(65536)
                    if not data:
                        break
                    ws.send(data)
            except Exception:
                pass
            finally:
                stop.set()

        t = threading.Thread(target=pump_upstream_to_client, daemon=True)
        t.start()
        try:
            while not stop.is_set():
                data = ws.receive(timeout=1)
                if data is None:  # timeout (keepalive) or client closed
                    if stop.is_set():
                        break
                    continue
                if isinstance(data, str):
                    data = data.encode()
                upstream.sendall(data)
        except Exception:
            pass
        finally:
            stop.set()
            try:
                upstream.close()
            except Exception:
                pass
