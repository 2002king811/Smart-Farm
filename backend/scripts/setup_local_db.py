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
HOST, PORT, USER = "localhost", "5432", "postgres"
TRIES = 3


def connect(password: str) -> psycopg.Connection:
    return psycopg.connect(
        host=HOST, port=PORT, user=USER, password=password, dbname="postgres", autocommit=True
    )


def ask_and_connect() -> tuple[psycopg.Connection, str] | None:
    # windows-install.bat sets this when it has just installed PostgreSQL itself.
    preset = os.environ.get("SF_PG_PASSWORD")
    for attempt in range(1, (1 if preset else TRIES) + 1):
        if preset:
            password = preset
        else:
            print("\nType the password you chose when you installed PostgreSQL, then press Enter.")
            print("(Nothing appears on screen while you type. That is normal.)")
            password = getpass.getpass("PostgreSQL password: ")
            if not password:
                print("The password was empty.")
                continue
        try:
            return connect(password), password
        except psycopg.OperationalError as exc:
            if "password authentication failed" in str(exc):
                print(f"That password is not right (try {attempt} of {TRIES}).")
                continue
            print(f"\nCould not connect to PostgreSQL: {exc}")
            print("Check that PostgreSQL is installed and running.")
            return None
    print("\nCould not sign in to PostgreSQL. If you have forgotten the password, ask for help.")
    return None


def main() -> int:
    if ENV_FILE.exists():
        print(f".env already exists ({ENV_FILE}); keeping it.")
        return 0

    result = ask_and_connect()
    if result is None:
        return 1
    conn, password = result

    with conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [DB_NAME]).fetchone()
        if exists:
            print(f"Database '{DB_NAME}' already exists.")
        else:
            conn.execute(f'CREATE DATABASE "{DB_NAME}"')
            print(f"Created database '{DB_NAME}'.")

    url = f"postgres://{quote(USER, safe='')}:{quote(password, safe='')}@{HOST}:{PORT}/{DB_NAME}"
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
