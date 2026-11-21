from rest_framework.routers import DefaultRouter


class Router(DefaultRouter):
    """Routes without trailing slashes, e.g. /api/v1/animals and /api/v1/animals/{id}."""

    include_root_view = False

    def __init__(self) -> None:
        super().__init__(trailing_slash="")  # type: ignore[arg-type]  # DRF accepts a str


router = Router()
