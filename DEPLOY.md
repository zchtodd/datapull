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
2. **Microsoft ODBC Driver 18 for SQL Server** (MSI from Microsoft) — `pyodbc` needs it.
3. **Memurai** (Windows-native Redis) — the Celery broker; runs as a service on `localhost:6379`.
4. An **external SQL Server** reachable from the VM, with a `datapull` database created.
5. If behind TLS interception, export the corporate root CA to `C:\certs\corp-root.pem`
   and set `PIP_CERT` / `SSL_CERT_FILE` to it so pip, Playwright's download, and the
   app's `urllib` Graph call validate.

### Steps

```powershell
# 1. Get the code onto the VM and cd into it (see transfer section below)
cd C:\datapull

# 2. Config: copy the template, generate fresh keys, fill in DATABASE_URL
Copy-Item deploy\windows\.env.native.example .env
#   SECRET_KEY:            python -c "import secrets; print(secrets.token_urlsafe(48))"
#   SECRET_ENCRYPTION_KEY: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   -> paste into .env, set DATABASE_URL to the external SQL Server. BACK UP the encryption key.

# 3. Install venv + deps + Chromium
.\deploy\windows\install.ps1

# 4. Apply migrations + create the admin login
.\deploy\windows\dbupgrade.ps1

# 5. Start web + worker + beat (IN the RDP session — headed browser needs the desktop)
.\deploy\windows\start-datapull.ps1
```

Open `http://localhost:5000/`, log in, and add the connections in the UI
(Sections 7–8 below apply the same way). Verify with
`.\.venv\Scripts\python.exe scripts\check_mfa_mailbox.py` after loading `.env`.

### Notes / caveats (native mode)

- **Run in the interactive session.** The Chromium windows are headed on the RDP
  desktop, so the worker must run in a logged-in session — not a session-0 Windows
  service. To survive logoff, use a **Scheduled Task set to run at logon** for
  `start-datapull.ps1` rather than an NSSM/session-0 service.
- **No in-app live view** — the VNC bridge was Docker/Xvfb-specific. You watch the
  browser directly on the desktop; the MFA prompt, progress, failures, and
  auto-resume UI all still work (they're plain HTTP).
- **Egress still required at runtime**: `login.microsoftonline.com`,
  `graph.microsoft.com`, `ciam.primetherapeutics.com`, `*.oktacdn.com`.
- Stop everything: `Get-Process waitress-serve, celery | Stop-Process`.

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
