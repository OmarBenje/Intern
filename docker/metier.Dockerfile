FROM python:3.12.15-slim-bookworm AS dependances
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
WORKDIR /app/metier
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.29
COPY metier/pyproject.toml metier/uv.lock metier/.python-version ./
RUN test "$(python -c 'import platform; print(platform.python_version())')" = "$(cat .python-version)" \
    && uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python

FROM python:3.12.15-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/metier
COPY --from=dependances /app/metier/.venv /app/metier/.venv
COPY metier/app /app/metier/app
COPY donnees/jeu_fictif.py donnees/cv_fictif.pdf donnees/verifier.py /app/donnees/
COPY docker/demarrer-metier.sh /app/docker/demarrer-metier.sh
RUN useradd --create-home --uid 10001 intern \
    && mkdir -p /app/.private-media /app/staticfiles \
    && for login in alice bob vide; do \
         install -d -m 0700 /app/.private-media/dev/$login; \
         install -m 0600 /app/donnees/cv_fictif.pdf /app/.private-media/dev/$login/cv.pdf; \
       done \
    && chown -R intern:intern /app/.private-media /app/staticfiles
USER intern
EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker/demarrer-metier.sh"]
CMD [".venv/bin/gunicorn", "--chdir", "app", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "--access-logfile", "-", "--error-logfile", "-"]
