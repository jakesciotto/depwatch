FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY config.toml ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" DEPWATCH_DATA_DIR=/data
VOLUME /data
CMD ["depwatch", "serve"]
