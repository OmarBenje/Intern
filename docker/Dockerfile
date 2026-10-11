FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app/metier
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.9.29
COPY metier/pyproject.toml metier/uv.lock ./
RUN uv sync --frozen --no-dev
COPY metier/app /app/metier/app
RUN useradd --create-home --uid 10001 intern && mkdir -p /app/.private-media /app/staticfiles && chown -R intern:intern /app
USER intern
EXPOSE 8000
CMD [".venv/bin/gunicorn", "--chdir", "app", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "90", "--access-logfile", "-"]
