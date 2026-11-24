# One image, several roles: api (gunicorn), websocket (uvicorn), worker and beat (celery).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home /app app

FROM base AS dev
COPY requirements/ requirements/
RUN pip install -r requirements/dev.txt
COPY . .
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS prod
COPY requirements/ requirements/
RUN pip install -r requirements/base.txt
COPY . .
RUN DJANGO_SECRET_KEY=build-only DATABASE_URL=sqlite:///tmp/x.db \
    DJANGO_SETTINGS_MODULE=config.settings.base python manage.py collectstatic --noinput \
    && mkdir -p /app/media && chown -R app:app /app
USER app
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
