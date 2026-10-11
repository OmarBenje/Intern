#!/usr/bin/env bash
# Dans vm-metier, root, après restauration SQL sur vm-donnees.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv git build-essential postgresql-client-16
id intern >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/intern --shell /usr/sbin/nologin intern
install -d -m 0750 -o intern -g intern /var/lib/intern/private-media
install -d -m 0750 -o intern -g intern /var/cache/intern-uv
python3 -m venv /opt/intern-tools
/opt/intern-tools/bin/pip install uv==0.11.29
install -m 0755 /opt/intern-tools/bin/uv /usr/local/bin/uv
chown -R intern:intern /opt/intern
chown root:intern /etc/intern/intern.env
chmod 0640 /etc/intern/intern.env
runuser -u intern -- env UV_CACHE_DIR=/var/cache/intern-uv UV_PYTHON_DOWNLOADS=never \
    uv sync --project /opt/intern/metier --frozen --no-dev --python /usr/bin/python3
set -a
source /etc/intern/intern.env
set +a
runuser -u intern -- /opt/intern/metier/.venv/bin/python /opt/intern/metier/app/manage.py check
runuser -u intern -- /opt/intern/metier/.venv/bin/python /opt/intern/metier/app/manage.py migrate --noinput
runuser -u intern -- /opt/intern/metier/.venv/bin/python /opt/intern/metier/app/manage.py collectstatic --noinput
for login in alice bob vide; do
    install -d -m 0700 -o intern -g intern "/var/lib/intern/private-media/dev/$login"
    install -m 0600 -o intern -g intern /opt/intern/donnees/cv_fictif.pdf "/var/lib/intern/private-media/dev/$login/cv.pdf"
done
export PGHOST="$POSTGRES_HOST" PGPORT="$POSTGRES_PORT" PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" PGPASSWORD="$POSTGRES_PASSWORD"
runuser -u intern -- /opt/intern/metier/.venv/bin/python /opt/intern/donnees/verifier.py
install -m 0644 /opt/intern/deploiement/metier/intern.service /etc/systemd/system/intern.service
systemd-analyze verify /etc/systemd/system/intern.service
systemctl daemon-reload
systemctl enable --now intern
systemctl is-active intern
