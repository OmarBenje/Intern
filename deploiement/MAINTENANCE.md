# Maintenance des VM et des campagnes de mesure

Ce guide décrit la maintenance des trois VM locales et la protection contre
les mises à jour concurrentes pendant les mesures. La maintenance possède sa
propre commande, indépendante des étapes du cours dans [EXECUTION.md](../EXECUTION.md).
L’installation des trois couches reste décrite dans [DEPLOIEMENT.md](DEPLOIEMENT.md).

## Prérequis

Les trois VM doivent être installées, avec un accès SSH administrateur
fonctionnel. Utiliser la configuration existante dans
`../.local-vms/access/ssh-etape8-interne.conf`, depuis la racine `Intern`.
Les clés et configurations réelles restent locales. Préciser `--config-ssh`
si le fichier SSH se trouve ailleurs.

Avant une maintenance, vérifier les sauvegardes PostgreSQL, les fichiers privés
et la configuration, ainsi que la procédure de restauration. Choisir un moment
où aucune campagne de mesure n’est active : la maintenance peut interrompre
l’application et redémarrer les invités.

## Vérifier et mettre à jour les trois VM

Depuis la racine `Intern` :

```bash
# État des opérations, des mises à jour et des redémarrages requis :
python3 deploiement/maintenance.py statut --vm

# Installer les mises à jour et vérifier les services :
python3 deploiement/maintenance.py executer --vm
```

Ce mode démarre les VM nécessaires, utilise les clés et la configuration SSH
existantes, redémarre les invités si requis, puis remet à l’arrêt uniquement les
VM initialement éteintes. Les VM privées utilisent un tunnel SOCKS temporaire
pour APT ; aucun NAT ni route par défaut n’est ajouté.

Les mises à jour s’exécutent dans une unité systemd invitée : une déconnexion
SSH ne tue pas dpkg. Une opération active est laissée finir. Les mises à jour
APT ne remplacent pas un déploiement applicatif : elles ne publient pas un
nouveau commit et ne lancent pas les migrations Django.

Le rapport local est `.execution/maintenance-vm.json`. Les journaux invités sont
conservés dans `/var/lib/intern-maintenance/apt.log` et le dernier résultat dans
`/var/lib/intern-maintenance/last-update.json`. Les rapports locaux sont en UTC.
Après l’opération, contrôler les services et les parcours applicatifs avant
une nouvelle campagne de mesure.

## Récupérer une maintenance interrompue

Une pause possède un propriétaire et conserve les états initiaux des unités APT.
Ne pas supprimer les verrous dpkg et ne pas tuer une mise à jour active.
Consulter d’abord le statut et les journaux. Quand aucune autre opération n’est
active, rétablir explicitement les états :

```bash
python3 deploiement/maintenance.py restaurer --vm
```

## Version de Python applicative


La version exacte est fixée dans [metier/.python-version](../metier/.python-version),
actuellement **3.12.15**. Les deux images de base du Dockerfile métier doivent
correspondre à cette valeur ; le build le vérifie. L’installation VM utilise
un interpréteur géré distinct sous `/opt/intern/python`, avec les dépendances
de `uv.lock`. Le Python système Ubuntu reste sous la responsabilité d’APT.

Pour une VM déjà installée, la bascule se fait en maintenance, hors campagne :
installer l’interpréteur épinglé, préparer un environnement séparé, exécuter
les tests dans une base PostgreSQL temporaire, puis activer l’environnement.
Le helper [aligner_python_invite.py](scripts/aligner_python_invite.py)
s’exécute comme administrateur sur la VM métier :

```bash
python3 aligner_python_invite.py preparer --interpreter /chemin/python-3.12.15
# Après les tests, conserver leur succès dans .python-validation.json du nouvel environnement.
# Format : {"python": "3.12.15", "exit_code": 0}
python3 aligner_python_invite.py activer
```

La préparation utilise le cache uv local hors ligne et ne touche pas à
l’environnement actif. L’activation exige le marqueur de tests réussis,
conserve l’ancien environnement et revient à celui-ci si le nouveau service
ne démarre pas ou ne répond pas au contrôle de santé. Aucune migration ni
modification des données de référence n’est incluse dans cette bascule.

Le catalogue inclus dans uv 0.11.29 ne proposait pas Python 3.12.15.
L’installation utilise donc les métadonnées officielles épinglées d’uv 0.13.1,
sous `crates/uv-python-managed/download-metadata.json` ; l’ancien chemin
`crates/uv-python/download-metadata.json` n’existe plus à cette version.
Référence : [installation Python avec uv](https://docs.astral.sh/uv/guides/install-python/).
Les téléchargements et la maintenance restent séparés des mesures.
Le contrôleur de campagne refuse désormais toute différence de version Python,
y compris de correctif, en plus de Django, DRF et Gunicorn.
L’[intervention vérifiée du 18 octobre 2026](docs/alignement-python-20261018.md)
conserve les versions constatées, les résultats des tests et la remise en état.

## Protection pendant les mesures

Les essais de performance réutilisent uniquement la protection temporaire contre
les mises à jour concurrentes ; ils n’exécutent aucune maintenance APT.
Le mécanisme est défini dans [scripts/maintenance/](scripts/maintenance/) et
partagé avec le contrôleur de mesures.

Avant une mesure, le contrôleur attend la fin d’une opération de paquets déjà
engagée, suspend les unités de mises à jour concernées et conserve leur état
initial. Une incohérence dpkg ou un redémarrage requis impose une maintenance
avant de mesurer. Les versions de paquets restent contrôlées entre les séries.
À la fin, la politique initiale des mises à jour est restaurée.

Les incidents et leurs preuves sont décrits dans [mesure/INCIDENTS.md](../mesure/INCIDENTS.md).
