"""Waitress entry point for native (non-Docker) production on Windows.

Run it with the venv's interpreter:  .\.venv\Scripts\python.exe serve.py

This deliberately avoids the pip-generated `waitress-serve.exe` console-script
shim, which fails with "The system cannot find the file specified" when the venv
was created from Microsoft Store Python. gunicorn (the Docker image's CMD) is
Unix-only, so Windows uses waitress. Host/port overridable via WEB_HOST/WEB_PORT.
"""
import os

from waitress import serve

from wsgi import app

if __name__ == "__main__":
    serve(
        app,
        host=os.environ.get("WEB_HOST", "0.0.0.0"),
        port=int(os.environ.get("WEB_PORT", "5000")),
    )
