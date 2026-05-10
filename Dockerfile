FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared \
    && chmod +x /usr/local/bin/cloudflared

RUN curl -fsSL https://github.com/anomalyco/opencode/releases/latest/download/opencode-linux-x64.tar.gz \
    | tar -xz -C /usr/local/bin/ opencode

RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app app

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY bot/ ./bot/
COPY services/ ./services/
COPY bot.py .
RUN uv sync --frozen --no-dev

RUN chown -R app:app /app

USER app

CMD [".venv/bin/python", "bot.py"]
