# Deploying datapull to a Windows VM

Two deployment models:

- **Native (no Docker) — recommended for this VM.** Docker Desktop needs WSL2,
  which requires a **reboot** to enable — not possible here. Run the app directly
  on Windows: waitress (web) + Celery worker/beat + jobs as native Playwright
  subprocesses. See **[Native deployment](#native-no-docker-deployment)** below.
- **Docker.** The original container model, kept for reference/other hosts. See
  [Docker deployment](#docker-deployment).

Both assume a corporate network with **TLS interception** and **restricted
outbound egress** for non-browser processes.

---

## Native (no-Docker) deployment

Runs everything on the Windows host, no containers, no reboot. Jobs run as
`python run.py` subprocesses using the venv's Playwright, **headed on your RDP
desktop** (so you watch the browser directly — there's no in-app live view in
this mode). The launcher switches to this mode when `DATAPULL_LAUNCHER=native`.

### Prerequisites (install once, no reboot)

1. **Python 3.12** for Windows (from python.org; "Add to PATH").
2. **Microsoft ODBC Driver 18 for SQL Server** (MSI) — `pyodbc` needs it. *(Skip if
   you start on SQLite — see the SQLite note at the end.)*
3. **Memurai** (Windows-native Redis) — the Celery broker; runs as a service on
   `localhost:6379`. *(Only needed to actually run jobs; the web UI starts without it.)*
4. An **external SQL Server** reachable from the VM, with a `datapull` database
   created. *(Or start on SQLite to skip this.)*
5. If behind **TLS interception**, export the corporate root CA to
   `C:\certs\corp-root.pem` once, then reuse it everywhere:
   - git: `git config --global http.sslBackend schannel` (uses the Windows cert
     store, which already trusts it)
   - pip / Playwright: `$env:PIP_CERT` and `$env:NODE_EXTRA_CA_CERTS` = that file
   - the app's `urllib` Graph call uses the Windows cert store automatically.

> **The bundled `deploy\windows\*.ps1` scripts may be blocked by your execution
> policy.** You don't need them — the steps below are the same commands run by
> hand. Everything here is a cmdlet or an `.exe`, which execution policy does
> **not** block (it only blocks running script *files*). If you'd rather run the
> scripts: `Get-ChildItem deploy\windows\*.ps1 | Unblock-File` then invoke each
> with `powershell -ExecutionPolicy Bypass -File .\deploy\windows\<script>.ps1`.

### Steps (all run manually — no .ps1 needed)

```powershell
# 1. Get the code (HTTPS — SSH/port 22 is blocked on the VM, 443 works)
cd C:\datapull
git clone https://github.com/zchtodd/datapull.git .
#   if git errors on the cert: git config --global http.sslBackend schannel  (then retry)
#   (or just extract datapull-deploy.zip here instead of cloning)

# 2. Create the config file from the template
Copy-Item deploy\windows\.env.native.example .env
#   generate the two secrets (stdlib only):
python -c "import secrets; print(secrets.token_urlsafe(48))"                             # -> SECRET_KEY
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"   # -> SECRET_ENCRYPTION_KEY
notepad C:\datapull\.env
#   paste both keys, set DATABASE_URL. BACK UP SECRET_ENCRYPTION_KEY.

# 3. Virtual env + dependencies (call the venv python by path — avoids Activate.ps1)
python -m venv .venv
#   behind TLS interception, set these first:
#     $env:PIP_CERT = "C:\certs\corp-root.pem"; $env:NODE_EXTRA_CA_CERTS = "C:\certs\corp-root.pem"
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium

# 4. Load .env into THIS shell (PowerShell doesn't auto-load it)
Get-Content .\.env | ForEach-Object { if ($_ -match '^\s*([^#=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim()) } }
$env:DATAPULL_LAUNCHER = "native"

# 5. Migrations + admin login
.\.venv\Scripts\python.exe -m flask --app wsgi db upgrade
.\.venv\Scripts\python.exe -m flask --app wsgi bootstrap-admin

# 6. Start web + worker + beat, IN your RDP session (headed browser needs the
#    desktop). Invoke the venv python by ABSOLUTE path with -WorkingDirectory —
#    do NOT use the .venv\Scripts\*.exe console-script shims (they fail with
#    "cannot find the file specified" under Microsoft Store Python). -PassThru
#    captures the PIDs so you can stop them without killing every python.exe.
$py = "C:\datapull\.venv\Scripts\python.exe"
$web    = Start-Process $py -PassThru -WorkingDirectory C:\datapull -ArgumentList "serve.py"
$worker = Start-Process $py -PassThru -WorkingDirectory C:\datapull -ArgumentList "-m","celery","-A","celery_worker.celery_app","worker","--loglevel=info","--pool=threads","--concurrency=4"
$beat   = Start-Process $py -PassThru -WorkingDirectory C:\datapull -ArgumentList "-m","celery","-A","celery_worker.celery_app","beat","--loglevel=info","--schedule","$env:TEMP\celerybeat-schedule"
"web=$($web.Id) worker=$($worker.Id) beat=$($beat.Id)"
```

Open `http://localhost:5000/`, log in, and add the connections in the UI
(Sections 7–8 below). Smoke-test the mailbox provider (after step 4's `.env`
load) with:
`.\.venv\Scripts\python.exe scripts\check_mfa_mailbox.py`

> The `Start-Process` calls in step 6 inherit the environment you set in step 4,
> so run steps 4→6 in the **same** PowerShell window.

### Notes / caveats (native mode)

- **Run in the interactive session.** Chromium is headed on the RDP desktop, so the
  worker must run in a logged-in session — not a session-0 Windows service. To
  survive logoff, create a **Scheduled Task set to run at logon** that runs the
  step-4 env load + the three `Start-Process` lines (as commands, so no `.ps1`
  execution-policy issue).
- **Use `python.exe` (+ `serve.py` / `-m celery`), not the `*.exe` shims.** The
  pip-generated `waitress-serve.exe` / `celery.exe` in `.venv\Scripts` break under
  Microsoft Store Python. The durable fix is to install Python from python.org and
  recreate the venv; the module/`serve.py` form above works either way.
- **No in-app live view** — the VNC bridge was Docker/Xvfb-specific. You watch the
  browser directly on the desktop; the MFA prompt, progress, failures, and
  auto-resume UI all still work (plain HTTP).
- **Egress still required at runtime**: `login.microsoftonline.com`,
  `graph.microsoft.com`, `ciam.primetherapeutics.com`, `*.oktacdn.com`.
- **Stop everything**: use the PIDs printed in step 6 —
  `Stop-Process -Id $web.Id,$worker.Id,$beat.Id` (they're all `python.exe`, so
  don't `Stop-Process -Name python` — that would kill unrelated Python too).
- **Start on SQLite to defer SQL Server / ODBC / Memurai**: set
  `DATABASE_URL=sqlite:///C:/datapull/datapull.db` in `.env`. The web UI, login,
  and migrations work immediately with no DB install; running jobs still needs
  Memurai + the worker.

### Run as Windows services (headless, survives sign-out + reboot)

The interactive/headed setup above dies when you sign out. To run unattended,
register the three processes as **NSSM services** and run the browser
**headless** (session 0 has no desktop). Trade-off: headless may be challenged
by Okta more than headed.

**Extra prerequisites**
- **NSSM** (`nssm.exe` on PATH — https://nssm.cc).
- In `.env`: **`PARAM_HEADED=false`** and **`PLAYWRIGHT_BROWSERS_PATH=C:\datapull\ms-playwright`**
  (both are in `.env.native.example`).
- Install Chromium to that **shared** path (a LocalSystem service can't see
  browsers installed under your user profile):
  ```powershell
  $env:PLAYWRIGHT_BROWSERS_PATH = "C:\datapull\ms-playwright"
  .\.venv\Scripts\python.exe -m playwright install chromium
  ```

**Install the services** (elevated cmd — "Run as administrator"):
```bat
deploy\windows\install-services.bat
```
That registers `datapull-web` / `datapull-worker` / `datapull-beat`, sets
`AppDirectory` to the repo root (so each loads `.env` automatically), auto-start
on boot, restart-on-crash, worker/beat depending on Memurai, and logs to
`C:\datapull\logs\`. Then it's live at `http://localhost:5000/` and keeps running
across sign-out and reboot.

**Manage / remove**
```bat
nssm restart datapull-worker      &  sc query datapull-web      &  nssm status datapull-beat
deploy\windows\uninstall-services.bat
```

Notes:
- Services run as **LocalSystem** by default. Headless Chromium under LocalSystem
  usually works with the shared browsers path above; if it doesn't, set the
  services to run as a dedicated user that has a profile —
  `nssm set datapull-worker ObjectName .\svcuser <password>`.
- LocalSystem must be able to reach the external SQL Server and Graph/Okta; if
  egress is proxy-only, add `HTTP_PROXY`/`HTTPS_PROXY` to `.env`.
- Update flow: `git pull`, then `nssm restart datapull-web datapull-worker datapull-beat`
  (and `... flask db upgrade` first if there are new migrations).

---

## Docker deployment

The container model, for reference or non-Windows hosts. On this reboot-blocked
VM, prefer the native path above. Because of the egress restriction, the reliable
Docker route is **Path A**: build the images on a machine that already has working
internet, ship them to the VM, and `docker load`. **Path B** (build on the VM)
only works if the VM's Docker can reach Docker Hub / PyPI / MCR.

---

## 0. Prerequisites on the VM

- Docker Desktop installed, **Settings → General → Use the WSL 2 based engine** on,
  and **Linux containers** (not Windows containers) selected.
- Disable **sleep/hibernate** (Power settings) and confirm the Windows clock is
  syncing — cookies/TLS depend on a correct clock.
- A folder for the app, e.g. `C:\datapull`.

---

## 1. Get the code onto the VM

Use the byte-preserving zip (not `git clone` on Windows — that can rewrite
`entrypoint.sh` to CRLF and break the browser container). Transfer
`datapull-deploy.zip` via whatever channel works (RDP clipboard paste, SCP over
OpenSSH, or an internal file share), copy it **local to the VM first**, then:

```powershell
Expand-Archive -Path C:\datapull\datapull-deploy.zip -DestinationPath C:\datapull
cd C:\datapull
```

---

## 2A. (Recommended) Build images off-VM and ship them

On a machine **with** working internet + Docker (your dev box):

```bash
# build the two app images
docker build -f Dockerfile -t datapull-app .
docker build -f docker/browser/Dockerfile -t datapull-browser .
# pull the base images the stack runs
docker pull redis:7-alpine
docker pull mcr.microsoft.com/mssql/server:2022-latest
docker pull tecnativa/docker-socket-proxy:0.2
# save all five into one tarball
docker save -o datapull-images.tar \
  datapull-app datapull-browser redis:7-alpine \
  mcr.microsoft.com/mssql/server:2022-latest tecnativa/docker-socket-proxy:0.2
gzip datapull-images.tar          # ~2-3 GB compressed
```

Transfer `datapull-images.tar.gz` to the VM (SCP or a file share — it's too big
for clipboard/base64). On the VM:

```powershell
# if gzipped:
tar -xzf datapull-images.tar.gz          # -> datapull-images.tar  (Windows ships tar.exe)
docker load -i datapull-images.tar
docker images                            # confirm all five are present
```

> Runtime TLS note: if the corporate proxy intercepts **graph.microsoft.com** /
> **login.microsoftonline.com**, the worker's Graph MFA call (Python `urllib`)
> will fail cert validation. If so, rebuild `datapull-app` with the corporate
> root CA baked in (see the CA snippet in Path B) — the browser already tolerates
> interception via `ignore_https_errors`, but `urllib` does not.

Skip to **Section 3**.

## 2B. (Alternative) Build on the VM

Only if the VM's Docker can reach Docker Hub, PyPI, and MCR. Because of TLS
interception you must trust the corporate root CA inside the images or `pip`/`apt`
fail. Export the CA once (see `README`/earlier notes) to `corp-root.pem` in the
project root, then add to **both** `Dockerfile` and `docker/browser/Dockerfile`
before the first `apt-get`/`pip` line:

```dockerfile
COPY corp-root.pem /usr/local/share/ca-certificates/corp-root.crt
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
```

Then build:

```powershell
docker compose -f docker-compose.prod.yml --profile build build
```

`update-ca-certificates` also fixes the app's runtime `urllib` Graph call, since
Python's OpenSSL reads that same bundle.

---

## 3. Create the production `.env`

In `C:\datapull` (next to `docker-compose.prod.yml`). **Do not reuse the dev
`.env`** — generate fresh keys:

```powershell
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('SECRET_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

`.env` contents:

```
SECRET_KEY=<first command output>
SECRET_ENCRYPTION_KEY=<second command output>
MSSQL_SA_PASSWORD=<a strong password meeting SQL Server complexity rules>
```

> ⚠️ **Back up `SECRET_ENCRYPTION_KEY` now, somewhere safe.** Every stored
> connection secret (Graph client secret, portal password) is encrypted with it.
> If it's lost or changed, all saved credentials become permanently
> undecryptable and every job breaks.

---

## 4. Start the stack

```powershell
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps        # all services Up; db healthy
```

(If you used Path A, images are already loaded, so `up` won't rebuild. If Path B,
you already ran `--profile build build`.)

---

## 5. Initialize the database and admin login

```powershell
# apply the schema (db-init only creates the empty database)
docker compose -f docker-compose.prod.yml run --rm web flask --app wsgi db upgrade
# create the operator login (uses ADMIN_EMAIL / ADMIN_PASSWORD if set, else prompts)
docker compose -f docker-compose.prod.yml run --rm web flask --app wsgi bootstrap-admin
```

---

## 6. Verify

```powershell
# health endpoint
curl.exe http://localhost:5000/api/health          # {"status":"ok"} (or 200)
docker compose -f docker-compose.prod.yml logs --tail=50 web
```

Open `http://localhost:5000/` on the VM, log in with the admin account. Front it
with a TLS reverse proxy (nginx/caddy/IIS) before exposing it beyond the VM — it
speaks plain HTTP with login credentials.

---

## 7. Re-enter connections in the UI

Because the Fernet key is new, previously stored secrets don't carry over. In the
web UI, recreate:

- the **MFA mailbox** connection (`is_mfa`): `tenant_id`, `client_id`,
  `client_secret`, `mailbox`, `from_contains` — the Entra app needs Graph
  **Application** permission **Mail.Read** with admin consent.
- the **portal account** connection: `LOGIN_URL`, `ACCOUNT_USERNAME`,
  `ACCOUNT_PASSWORD`.

Attach both to the Prime job definition and enable **Auto-resume** if desired.

---

## 8. Confirm runtime egress

The app must reach, from inside the containers:

- `login.microsoftonline.com`, `graph.microsoft.com` (MFA auto-retrieval)
- `ciam.primetherapeutics.com`, `*.oktacdn.com` (the portal + sign-in widget)

If the corporate egress is proxy-only, add to the `web` and `worker` services in
`docker-compose.prod.yml`:

```yaml
    environment:
      - HTTP_PROXY=http://PROXYHOST:PORT
      - HTTPS_PROXY=http://PROXYHOST:PORT
      - NO_PROXY=localhost,127.0.0.1,web,redis,db,docker-proxy
```

and pass a proxy to the launched browser (Chromium) via the launcher's args if
needed. The quickest end-to-end check is `scripts/check_mfa_mailbox.py`:

```powershell
docker compose -f docker-compose.prod.yml exec worker python /app/scripts/check_mfa_mailbox.py
```

---

## 9. Operations

- **Restart policy**: all long-running services use `restart: unless-stopped`, so
  they come back after a crash or VM reboot.
- **Backups**: the `mssql-data` and `outputs` Docker volumes, plus `.env` (and its
  `SECRET_ENCRYPTION_KEY`). Example DB volume backup:
  ```powershell
  docker run --rm -v datapull_mssql-data:/data -v C:\backups:/backup alpine tar czf /backup/mssql-data.tgz -C /data .
  ```
- **Logs**: capped by the compose `json-file` driver (10 MB × 5 per service).
- **Updates**: transfer a new image tarball (Path A) or re-`build` (Path B),
  `docker compose -f docker-compose.prod.yml up -d`, then re-run
  `... db upgrade` for any new migrations.
- **Disk**: `outputs` grows with every run (invoices + failure screenshots) — plan
  a retention/cleanup policy.
