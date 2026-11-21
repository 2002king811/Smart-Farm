"""Local setup helper (used by windows-setup.bat): checks the PostgreSQL password, creates the
`smartfarm` database if needed and writes the project's .env for simple local mode."""

import getpass
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
DB_NAME = "smartfarm"


def main() -> int:
    if ENV_FILE.exists():
        print(f".env already exists ({ENV_FILE}); keeping it.")
        return 0

    preset = os.environ.get(
        "SF_PG_PASSWORD"
    )  # set by windows-install.bat after it installs PostgreSQL
    if preset:
        host, port, user, password = "localhost", "5432", "postgres", preset
    else:
        host = input("PostgreSQL host [localhost]: ").strip() or "localhost"
        port = input("PostgreSQL port [5432]: ").strip() or "5432"
        user = input("PostgreSQL user [postgres]: ").strip() or "postgres"
        password = getpass.getpass("PostgreSQL password (the one you chose when installing): ")

    try:
        conn = psycopg.connect(
            host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True
        )
    except psycopg.OperationalError as exc:
        print(f"\nCould not connect to PostgreSQL: {exc}")
        print("Check that PostgreSQL is installed and running, and that the password is right.")
        return 1

    with conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [DB_NAME]).fetchone()
        if exists:
            print(f"Database '{DB_NAME}' already exists.")
        else:
            conn.execute(f'CREATE DATABASE "{DB_NAME}"')
            print(f"Created database '{DB_NAME}'.")

    url = f"postgres://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/{DB_NAME}"
    ENV_FILE.write_text(
        "# Written by windows-setup.bat. Simple local mode: no Redis or Docker needed.\n"
        "DJANGO_SETTINGS_MODULE=config.settings.dev\n"
        f"DJANGO_SECRET_KEY={secrets.token_urlsafe(48)}\n"
        f"DATABASE_URL={url}\n"
        "USE_REDIS=false\n"
        "EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend\n"
    )
    print(f"Wrote {ENV_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
