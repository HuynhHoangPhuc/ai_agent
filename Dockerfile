FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY . /app

WORKDIR /app

RUN uv sync --locked

CMD ["/app/.venv/bin/fastapi", "run", "app/client.py", "--port", "80", "--host", "0.0.0.0"]
