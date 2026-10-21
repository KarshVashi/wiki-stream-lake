# Build from the repo root so uv.lock is available:
#   docker build --platform linux/arm64 -f src/producer/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group producer && rm /bin/uv

COPY src/producer ./producer

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER nobody
ENTRYPOINT ["python", "-m", "producer"]
