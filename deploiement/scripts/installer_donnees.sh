#!/usr/bin/env bash
# Dans vm-donnees, root ; fichiers transférés dans /var/tmp/intern-etape9.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y postgresql-16 postgresql-contrib-16 nftables
psql --version
work=/var/tmp/intern-etape9
test -f "$work/donnees/schema.sql"
test -f "$work/donnees/data.sql"
test -f /etc/intern/database-password

# Refuser de modifier une base existante.
if [[ $(runuser -u postgres -- psql -XAt -c "SELECT count(*) FROM pg_database WHERE datname='intern'") != 0 ]]; then
    echo 'La base intern existe déjà : inspecter son état avant de reprendre.' >&2
    exit 1
fi
db_password=$(cat /etc/intern/database-password)
[[ "$db_password" =~ ^[a-f0-9]{64}$ ]]
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 <<SQL
CREATE ROLE intern_user LOGIN PASSWORD '$db_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE intern OWNER intern_user;
SQL
unset db_password
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 --dbname=intern \
    -c 'SET ROLE intern_user' -f "$work/donnees/schema.sql" -f "$work/donnees/data.sql"
install -m 0644 "$work/deploiement/donnees/intern.conf" /etc/postgresql/16/main/conf.d/intern.conf
cp -n /etc/postgresql/16/main/pg_hba.conf /etc/postgresql/16/main/pg_hba.conf.pre-intern
install -m 0640 -o postgres -g postgres "$work/deploiement/donnees/pg_hba.conf" /etc/postgresql/16/main/pg_hba.conf
mkdir -p /etc/nftables.d
install -m 0644 "$work/deploiement/donnees/intern-db.nft" /etc/nftables.d/intern-db.nft
cp -n /etc/nftables.conf /etc/nftables.conf.pre-intern
printf '%s\n' '#!/usr/sbin/nft -f' 'flush ruleset' 'include "/etc/nftables.d/intern-db.nft"' > /etc/nftables.conf
nft -c -f /etc/nftables.conf
systemctl enable --now nftables
systemctl restart nftables
systemctl enable postgresql
systemctl restart postgresql@16-main
runuser -u postgres -- psql -X --dbname=intern -c 'SELECT count(*) AS comptes FROM auth_user; SELECT count(*) AS offres FROM jobboard_offer;'
rm -f /etc/intern/database-password
