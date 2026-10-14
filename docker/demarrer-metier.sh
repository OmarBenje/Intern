#!/bin/sh
# La base est initialisée par le service donnees, sans nouveau peuplement.
set -eu
.venv/bin/python app/manage.py check
.venv/bin/python app/manage.py migrate --check
.venv/bin/python app/manage.py collectstatic --noinput
exec "$@"
