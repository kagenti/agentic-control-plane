FROM quay.io/pdettori/python:3.12-slim

RUN apt-get update \
    && apt-get install -y git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.6.8 /uv /uvx /bin/

ADD . /app

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv uv sync

RUN chgrp -R 0 /app \
    && chmod -R g=u /app

ENV PATH="/app/.venv/bin:$PATH"

USER 1001

CMD ["uv", "run", "server", "--host", "0.0.0.0"]
