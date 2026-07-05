# datapull

Flask + Celery + Redis backend, containerized with Docker Compose for local development.
Serves both a server-rendered web UI and a JSON API.

## Layout

```
app/
  __init__.py      # Flask app factory (SQLAlchemy + Migrate + Celery)
  config.py        # config from environment variables
  extensions.py    # shared db (SQLAlchemy) and migrate (Flask-Migrate) instances
  models.py        # SQLAlchemy models
  routes.py        # web UI (bp) + JSON API (api, under /api)
  tasks.py         # Celery tasks
  templates/       # Jinja2 templates for the web UI
migrations/        # Alembic migration environment + versions/
wsgi.py            # Flask entry point (web)
celery_worker.py   # Celery entry point (worker)
Dockerfile
docker-compose.yml
```

## Routes

| Method | Path                  | Description                       |
| ------ | --------------------- | --------------------------------- |
| GET    | `/`                   | Hello-world web UI (HTML)         |
| GET    | `/api/health`         | Health check (JSON)               |
| POST   | `/api/jobs?seconds=N` | Start a long-running job (JSON)   |
| GET    | `/api/jobs/<task_id>` | Poll a job's status (JSON)        |

## Run locally (Docker)

```bash
docker compose up --build
```

Starts: `web` (Flask), `worker` (Celery), `redis`, `db` (SQL Server 2022), and a
one-shot `db-init` that creates the `datapull` database once SQL Server is healthy.
Open <http://localhost:5000/> for the UI.

## Database & migrations

The app uses SQLAlchemy (Flask-SQLAlchemy) against SQL Server via pyodbc + the
Microsoft ODBC Driver 18, with Alembic migrations driven by Flask-Migrate.
Migrations are **run by hand** — they are not applied automatically on startup.

```bash
# apply all migrations (run against the running stack)
docker compose run --rm web flask --app wsgi db upgrade

# after changing a model, autogenerate a new migration...
docker compose run --rm web flask --app wsgi db migrate -m "describe change"
# ...review the generated file under migrations/versions/, then upgrade:
docker compose run --rm web flask --app wsgi db upgrade

# roll back the most recent migration
docker compose run --rm web flask --app wsgi db downgrade -1
```

Connection settings come from `DATABASE_URL` / `MSSQL_SA_PASSWORD` (see `.env.example`).

## Try the API

```bash
# kick off a long-running job (default 10s)
curl -X POST "http://localhost:5000/api/jobs?seconds=5"
# => {"task_id": "..."}

# poll its status
curl "http://localhost:5000/api/jobs/<task_id>"
```

## Run without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# terminal 1: redis (or run the redis container)
redis-server

# terminal 2: worker
celery -A celery_worker.celery_app worker --loglevel=info

# terminal 3: web
flask --app wsgi run --debug
```
