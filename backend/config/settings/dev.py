from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
LOG_FORMAT = env("LOG_FORMAT", default="text")
LOGGING["handlers"]["console"]["formatter"] = LOG_FORMAT  # type: ignore[index] # noqa: F405
