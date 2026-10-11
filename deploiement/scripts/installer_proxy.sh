#!/usr/bin/env bash
# Dans vm-proxy, root ; le build React et les statiques Django sont déjà transférés.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y nginx
test -f /var/www/intern/client/index.html
test -d /var/www/intern/static/admin
install -m 0644 /var/tmp/intern-etape9/deploiement/proxy/intern.conf /etc/nginx/sites-available/intern
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/intern /etc/nginx/sites-enabled/intern
nginx -t
systemctl enable nginx
systemctl restart nginx
systemctl is-active nginx
