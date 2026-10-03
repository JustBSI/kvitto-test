FROM python:3.14-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

RUN useradd --create-home appuser
USER appuser

CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]

FROM app AS tests
USER root
RUN pip install --no-cache-dir '.[dev]'
COPY tests ./tests
USER appuser
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider"]
