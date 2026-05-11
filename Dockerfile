FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# -------------------------
# System dependencies
# -------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# -------------------------
# cloudflared
# -------------------------
RUN curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared \
    && chmod +x /usr/local/bin/cloudflared

# -------------------------
# opencode
# -------------------------
RUN curl -fsSL https://github.com/anomalyco/opencode/releases/latest/download/opencode-linux-x64.tar.gz \
    | tar -xz -C /usr/local/bin/ opencode

# -------------------------
# Non-root user
# -------------------------
RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app

# -------------------------
# App directory
# -------------------------
WORKDIR /app

# Make /app and cache writable for app user
RUN mkdir -p /app && chown -R app:app /app

# -------------------------
# Python deps (layered install)
# -------------------------
COPY --chown=app:app pyproject.toml uv.lock ./

# IMPORTANT: force uv cache to writable location
ENV UV_CACHE_DIR=/tmp/uv-cache
RUN mkdir -p /tmp/uv-cache && chown -R app:app /tmp/uv-cache

USER app

RUN uv sync --frozen --no-dev --no-install-project

# -------------------------
# Copy source
# -------------------------
COPY --chown=app:app bot/ ./bot/
COPY --chown=app:app services/ ./services/
COPY --chown=app:app bot.py .

RUN uv sync --frozen --no-dev

# -------------------------
# Runtime
# -------------------------
CMD ["uv", "run", "bot.py"]