"""Install an isolated measurement service on existing VMs; never replace production settings."""

import argparse
from pathlib import Path
import subprocess

DATABASE = "intern_mesure17"
WORK = Path("/opt/intern-mesure17")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["donnees", "metier", "proxy"])
    args = parser.parse_args()
    marker = WORK / ".measurement-owned"
    if args.role == "donnees":
        hba = Path("/etc/postgresql/16/main/pg_hba.conf")
        backup = hba.with_name("pg_hba.conf.before-mesure17")
        if backup.exists() and not marker.exists():
            raise RuntimeError("Existing PostgreSQL backup is not owned by this measurement setup")
        if not backup.exists():
            backup.write_bytes(hba.read_bytes())
            backup.chmod(0o600)
        marker.touch()
        rule = "host intern_mesure17 intern_user 10.10.10.20/32 scram-sha-256\n"
        original = backup.read_text()
        hba.write_text(rule + original)
        run("systemctl", "reload", "postgresql@16-main")
        return
    if args.role == "metier":
        if not marker.exists() and any(path.exists() for path in [Path("/etc/intern/mesure17.env"), Path("/etc/systemd/system/intern-mesure17.service")]):
            raise RuntimeError("Refuse to replace an existing measurement service")
        marker.touch()
        original = Path("/etc/intern/intern.env")
        values = {}
        for line in original.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"').strip("'")
        values.update({
            "AUTH_LOGIN_RATE_LIMIT_ENABLED": "false",
            "POSTGRES_DB": DATABASE, "DJANGO_DEBUG": "true",
            "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1,10.10.10.20",
            "CSRF_TRUSTED_ORIGINS": "http://127.0.0.1:8081,http://localhost:8081",
            "PUBLIC_BASE_URL": "http://127.0.0.1:8081", "INTERN_ROOT": str(WORK),
            "PRIVATE_STORAGE_BACKEND": "local", "PRIVATE_STORAGE_ROOT": "/var/lib/intern-mesure17/private-media",
        })
        env = Path("/etc/intern/mesure17.env")
        env.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        env.chmod(0o640)
        run("chown", "root:intern", str(env))
        run("install", "-d", "-o", "intern", "-g", "intern", "/var/lib/intern-mesure17/private-media")
        run("chown", "-R", "intern:intern", str(WORK))
        unit = Path("/etc/systemd/system/intern-mesure17.service")
        unit.write_text("""[Unit]
Description=Intern isolated measurement API
After=network-online.target
[Service]
User=intern
Group=intern
WorkingDirectory=/opt/intern-mesure17/metier/app
EnvironmentFile=/etc/intern/mesure17.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/intern/metier/.venv/bin/gunicorn --bind 10.10.10.20:8001 --workers 2 --timeout 30 --access-logfile - --error-logfile - config.wsgi:application
Restart=on-failure
NoNewPrivileges=true
""")
        run("systemctl", "daemon-reload")
        return
    config = Path("/etc/nginx/conf.d/mesure17.conf")
    if config.exists() and not marker.exists():
        raise RuntimeError("Refuse to replace an existing Nginx configuration")
    marker.touch()
    config.write_text("""server {
    listen 10.10.10.10:8082;
    listen 10.0.3.15:8082;
    server_name localhost 127.0.0.1;
    root /opt/intern-mesure17/client;
    location ~ ^/(api/|admin/|health/) {
        proxy_pass http://10.10.10.20:8001;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
    location /static/ { alias /opt/intern-mesure17/static/; }
    location / { try_files $uri $uri/ /index.html; }
}
""")
    run("nginx", "-t")
    run("systemctl", "reload", "nginx")


if __name__ == "__main__":
    main()
