FROM python:3.12-slim

WORKDIR /app

ARG ENVIRONMENT=dev
ENV ENVIRONMENT=${ENVIRONMENT}

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY config.${ENVIRONMENT}.yaml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh
RUN mkdir -p /var/log/app

CMD ["./entrypoint.sh"]
