FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# dev (défaut) inclut pytest ; en production : --build-arg REQUIREMENTS=base
ARG REQUIREMENTS=dev
COPY requirements/ requirements/
RUN pip install -r requirements/${REQUIREMENTS}.txt

COPY . .

# Utilisateur non-root ; dossiers de données inscriptibles (volumes nommés)
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/media /data/static \
    && chown -R app:app /data /app
USER app

EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
