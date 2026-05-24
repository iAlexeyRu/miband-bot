FROM python:3.11-slim

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt

COPY mi-fitness-python /app/mi-fitness-python
RUN pip install -e /app/mi-fitness-python

COPY miband_tracker /app/miband_tracker
COPY miband_sync.py /app/
COPY fitness_bot.py /app/

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /opt/miband-tracker/data \
    && chown -R app:app /app /opt/miband-tracker

USER app

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os; from pathlib import Path; p = Path(os.environ.get('DATA_DIR', '/opt/miband-tracker/data')); p.mkdir(parents=True, exist_ok=True); raise SystemExit(0 if os.access(p, os.W_OK) else 1)"

CMD ["python", "-u", "miband_sync.py"]
