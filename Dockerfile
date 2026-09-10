FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev
RUN groupadd -g 1000 depwatch && useradd -m -u 1000 -g 1000 depwatch \
    && chown -R depwatch:depwatch /app \
    && mkdir -p /data && chown depwatch:depwatch /data
ENV PATH="/app/.venv/bin:$PATH" DEPWATCH_DATA_DIR=/data HOME=/home/depwatch
VOLUME /data
USER depwatch
CMD ["depwatch", "serve"]
