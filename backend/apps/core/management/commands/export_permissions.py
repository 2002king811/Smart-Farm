import json
import sys
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core.permissions import MATRIX_PATH

DEFAULT_TARGET = (
    Path(__file__).resolve().parents[5] / "frontend" / "src" / "routes" / "permissions.json"
)


class Command(BaseCommand):
    help = "Copy the role/permission matrix to the frontend, or --check that the copy is current."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("target", nargs="?", default=str(DEFAULT_TARGET))
        parser.add_argument("--check", action="store_true")

    def handle(self, *args: Any, target: str, check: bool, **options: Any) -> None:
        source = json.loads(MATRIX_PATH.read_text())
        path = Path(target)
        if check:
            if not path.exists() or json.loads(path.read_text()) != source:
                raise CommandError(
                    f"{path} is out of date. Run: python manage.py export_permissions"
                )
            self.stdout.write("Permission matrix is in sync.")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(source, indent=2) + "\n")
        sys.stdout.write(f"Wrote {path}\n")
