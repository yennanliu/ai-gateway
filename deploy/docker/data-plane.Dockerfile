# LiteLLM proxy + our hooks (data plane). Built from the repo root context.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY . /app
# Install our hooks package plus litellm[proxy].
RUN uv sync --package aigw-hooks --extra proxy --frozen --no-dev

ENV AIGW_LITELLM_CONFIG=/app/litellm.config.yaml \
    AIGW_PROXY_PORT=4000
EXPOSE 4000

# entrypoint.sh runs `litellm --config ...`; custom_auth resolves hooks.auth.
CMD ["sh", "-c", "uv run --package aigw-hooks bash data-plane/litellm/entrypoint.sh"]
