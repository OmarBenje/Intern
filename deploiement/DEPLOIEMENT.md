# Étape 9 — Déployer les trois couches

## Objectif et prérequis

Installer les couches existantes sur les VM dont le réseau a été vérifié à
l'[étape 8](reseau/README.md), dans l'ordre **données → métier → proxy**.
L'installation utilise les scripts SQL livrés, le code Django et le build React.
Les adresses et les paramètres des services sont réglés par configuration.

Le poste de préparation doit disposer de Python 3, VirtualBox, OpenSSH, Node.js
20.19+ ou 22.12+ et npm. Les VM utilisent Ubuntu Server 24.04 LTS. Le répertoire
local des VM contient la clé d'administration et le fichier SSH de l'étape 8.
Il reste hors du dépôt ; les secrets et les journaux d'installation y sont conservés.

## Configurations livrées

| Couche | Fichiers | Destination |
| --- | --- | --- |
| Réseau | [Trois Netplan](reseau/README.md) | `/etc/netplan/50-cloud-init.yaml` |
| Données | [intern.conf](donnees/intern.conf) | `/etc/postgresql/16/main/conf.d/intern.conf` |
| Données | [pg_hba.conf](donnees/pg_hba.conf) | `/etc/postgresql/16/main/pg_hba.conf` |
| Données | [intern-db.nft](donnees/intern-db.nft) | `/etc/nftables.d/intern-db.nft`, chargé par nftables |
| Métier | [Environnement exemple](metier/intern.env.example) | `/etc/intern/intern.env`, valeurs réelles locales |
| Métier | [intern.service](metier/intern.service) | `/etc/systemd/system/intern.service` |
| Proxy | [intern.conf](proxy/intern.conf) | `/etc/nginx/sites-available/intern` |

Le service métier est **`config.wsgi:application`**, lancé par Gunicorn sur
`10.10.10.20:8000`, avec le compte système `intern` et deux workers.
PostgreSQL écoute uniquement sur `10.10.10.30:5432` ; la règle HBA autorise
`intern_user` dans `intern` seulement depuis `10.10.10.20/32`, avec SCRAM.
Le filtrage nftables refuse également le port 5432 aux autres sources.

Nginx écoute sur les deux adresses du proxy : `10.10.10.10:80` et
`10.0.3.15:80` (adresse NAT relevée à l'étape 8). Si cette dernière change,
adapter la configuration Nginx avant installation. Il sert le client et les
statiques Django, et relaie `/api/`, `/admin/` et `/health/` vers le métier.
Le Host d'origine, y compris le port 8080, est conservé pour les sessions et le CSRF.

## Démonstration HTTP et secrets

`DJANGO_DEBUG=true` est explicite pour cette démonstration HTTP locale : le code
existant lie les cookies sécurisés et la redirection HTTPS à ce paramètre.
Les origines CSRF autorisées sont `http://127.0.0.1:8080` et
`http://localhost:8080`. Le client est construit avec **`VITE_API_ROOT=/api/v1`**.
Cette configuration est destinée à la topologie de démonstration, pas à une
publication sur Internet.

Le script génère une clé Django et un mot de passe PostgreSQL aléatoires dans
`$VM_WORK/access/secrets-etape9.json`, avec les permissions `0600`. Il les
réutilise pour les phases suivantes. Ne pas supprimer ce fichier entre les phases.
Le fichier réel d'environnement est installé sur le métier en `0640`, propriétaire
root et groupe intern ; il n'est pas ajouté au dépôt. Le mot de passe temporairement
transféré à la VM données est supprimé après création du rôle.

Le jeu de démonstration est entièrement fictif et ses comptes sont documentés
dans [le guide des données](../donnees/README.md). Aucun worker d'import ni
d'envoi externe n'est lancé pour ce déploiement.

## Exécuter depuis la racine du dépôt

Définir le répertoire local des VM et rouvrir temporairement l'administration
sur le proxy. Les commandes suivantes partent de machines éteintes.

```bash
export VM_WORK="$HOME/VMs-intern"
VBoxManage modifyvm vm-proxy --natpf2 'ssh-verification,tcp,127.0.0.1,2221,,22'
for vm in vm-proxy vm-metier vm-donnees; do
  VBoxManage startvm "$vm" --type headless
done
```

Si les machines sont déjà démarrées, conserver `VM_WORK`, remplacer
`modifyvm` par `VBoxManage controlvm vm-proxy natpf2
'ssh-verification,tcp,127.0.0.1,2221,,22'` et ne pas relancer `startvm`.
Ne pas ajouter une redirection déjà présente.

Le script [deployer_etape9.py](scripts/deployer_etape9.py) prend le snapshot
correspondant avant installation, identifie l'interface NAT temporaire par sa MAC,
transfère les fichiers et exécute l'installateur de la couche.

### 1. Base PostgreSQL

```bash
python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" donnees
```

Snapshot : **`avant donnees`**. Un NAT est activé ponctuellement sur le second
adaptateur pour installer PostgreSQL 16. La base `intern` et le rôle `intern_user`
sont créés, puis `donnees/schema.sql` et `donnees/data.sql` sont exécutés dans
cet ordre. Le rôle propriétaire possède ses tables, sans privilèges de superutilisateur,
de création de base ou de rôle. La restauration refuse une base déjà présente.

Les scripts SQL sont exécutés avec `ON_ERROR_STOP` et leurs transactions internes.
Le client PostgreSQL doit reconnaître les commandes `\restrict` des exports.
Après installation des configurations, PostgreSQL et nftables sont activés au
démarrage. Le Netplan temporaire et le second adaptateur NAT sont retirés ;
la VM est redémarrée et le service est vérifié.

Installateur invité : [installer_donnees.sh](scripts/installer_donnees.sh).
Les configurations antérieures sont sauvegardées avant remplacement.

### 2. API Django

```bash
python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" metier
```

Snapshot : **`avant metier`**. Le NAT ponctuel permet d'installer Python, Git,
les outils de compilation et `uv==0.11.29`. Les dépendances sont installées dans
`/opt/intern/metier/.venv` avec `uv sync --frozen --no-dev`, depuis le fichier
`uv.lock` livré et Python système. Le code est déposé sous `/opt/intern`.

Le script effectue le contrôle Django, la vérification/application des migrations
après restauration SQL, puis `collectstatic`. Les CV fictifs sont copiés dans
le stockage privé, avec accès limité au compte intern. Le vérificateur SQL
existant est exécuté depuis le métier ; ses écritures d'essai sont annulées.

Le service systemd est installé et activé. Le NAT ponctuel est retiré et la VM
est redémarrée ; `/health/ready/` doit répondre et prouve une requête réelle vers
PostgreSQL.

Installateur invité : [installer_metier.sh](scripts/installer_metier.sh).

### 3. Client React et Nginx

```bash
npm --prefix frontend ci
VITE_API_ROOT=/api/v1 npm --prefix frontend run build
python3 deploiement/scripts/deployer_etape9.py "$VM_WORK" proxy
```

Snapshot : **`avant proxy`**. Le client est construit sur le poste de préparation,
puis seuls les fichiers générés sont transférés dans `/var/www/intern/client`.
Les statiques Django collectés sur le métier sont transférés dans
`/var/www/intern/static`. Le proxy n'a pas besoin de Node.js pour servir le client.

Le site Nginx est installé, le site par défaut désactivé, et `nginx -t` exécuté.
Nginx est activé au démarrage et relancé.

Installateur invité : [installer_proxy.sh](scripts/installer_proxy.sh).

## Vérifier puis retirer l'administration temporaire

```bash
curl -f http://127.0.0.1:8080/health/ready/
curl -I http://127.0.0.1:8080/login
```

Ouvrir **`http://127.0.0.1:8080/login`**. La recette navigateur utilise les comptes
fictifs, les vrais services et les vrais appels HTTP. Définir `RECETTE_PASSWORD`
avec le mot de passe de démonstration indiqué dans le guide des données, puis :

```bash
RECETTE_URL=http://127.0.0.1:8080 node deploiement/scripts/recette_etape9.mjs
```

Vérifier les services après un redémarrage complet, les fichiers installés,
les snapshots et la topologie finale :

```bash
python3 deploiement/scripts/verifier_etape9.py "$VM_WORK" --redemarrer
```

Ce vérificateur utilise l'accès SSH temporaire, écrit les preuves et le manifeste
des empreintes, puis retire automatiquement cette redirection. Pour le relancer,
rouvrir d'abord l'accès avec `controlvm` comme indiqué plus haut. Si les contrôles
sont effectués manuellement, retirer cet accès avec
`VBoxManage controlvm vm-proxy natpf2 delete ssh-verification`.

La redirection HTTP `127.0.0.1:8080 → 80` reste conservée. Les VM métier et données
ne doivent avoir aucun NAT ni route par défaut. Les preuves finales figurent dans
le [rapport](docs/etape9.md) et les [sorties des contrôles](docs/preuves-etape9.txt).

Si une phase échoue, inspecter son journal et l'état de la couche avant reprise.
Le script ne détruit ni base ni VM et ne restaure pas automatiquement les snapshots.
Une reprise de la phase données sur une base existante est volontairement refusée.

Références : [PostgreSQL — HBA](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html),
[uv — synchronisation verrouillée](https://docs.astral.sh/uv/concepts/projects/sync/),
[Nginx — transmission des requêtes](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
