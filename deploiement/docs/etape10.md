# Étape 10 — Isolation, mesures et exports vérifiés

Les contrôles ont été exécutés le **12/10/2026** sur les trois VM réellement
déployées. Le [guide de vérification](../VERIFICATION.md) contient les commandes
reproductibles. Les snapshots **« avant verification »** sont conservés sur
chacune des trois machines.

## Matrice de joignabilité observée

| Depuis | Proxy :80 | Métier :8000 | Base :5432 |
| --- | --- | --- | --- |
| Hôte | Oui, via 127.0.0.1:8080 | Échec, délai de 2 s | Échec, délai de 2 s |
| vm-proxy | — | Oui | Échec, délai de 2 s |
| vm-metier | Oui | — | Oui |
| vm-donnees | Oui | Oui | — |

Les **neuf liaisons sont conformes**, dont les **trois accès interdits réellement
refusés**. Les refus ont été constatés par expiration des connexions TCP, pas
inférés de fichiers de configuration. La connexion PostgreSQL depuis le métier,
avec le compte applicatif et son mot de passe, retourne également `SELECT 1`.
Les sorties `ss -tlnp` confirment les écoutes : PostgreSQL sur `10.10.10.30:5432`,
Gunicorn sur `10.10.10.20:8000`, Nginx sur les deux adresses du proxy, port 80.

Preuves : [matrice brute](joignabilite-etape10.json) et
[sorties des commandes](preuves-etape10.txt). Seul le proxy conserve le NAT ;
les deux autres machines n'ont pas de route IPv4 par défaut.

## Mesures de référence

Trois séries complètes ont été effectuées : démarrage depuis les trois VM
éteintes, mémoire côté hôte au repos, empreinte des disques et dix consultations
par série. Le [tableau des mesures](mesures.md) donne les médianes, toutes les
séries, la configuration et les limites. Les
[valeurs brutes](mesures-etape10.json) permettent de refaire les calculs.

Le proxy est réglé en paravirtualisation minimal pour ces trois séries et pour
l'export, après un blocage du noyau sur une tentative avec default/KVM. Cette
[tentative échouée](incident-etape10.txt) est documentée séparément. Les ressources,
le réseau et le code applicatif sont inchangés.

## Trois OVA livrés

| Archive | Taille (octets) | Taille (Gio) | Contrôle |
| --- | ---: | ---: | --- |
| `vm-donnees.ova` | 1114041856 | 1.038 | Manifeste et lecture VirtualBox valides |
| `vm-metier.ova` | 1249764352 | 1.164 | Manifeste et lecture VirtualBox valides |
| `vm-proxy.ova` | 996657152 | 0.928 | Manifeste et lecture VirtualBox valides |

Les fichiers sont dans **`$VM_WORK/exports-etape10`**, hors du dépôt, avec
`SHA256SUMS`. Le [manifeste des exports](exports-etape10.json) contient les
empreintes SHA-256 complètes et le contenu de chaque archive. Les
[sorties VirtualBox](preuves-exports-etape10.txt) attestent les trois exports
et leur lecture avec `import --dry-run`.

Les exports ont été créés à partir de VM éteintes, sans redirection SSH
temporaire. Chaque empreinte OVF/VMDK du manifeste interne a été recalculée et
vérifiée. Les OVA représentent l'état courant installé ; l'arbre des snapshots
reste sur les VM originales. Le contrôle de lecture ne remplace pas un essai
de démarrage après réimportation, qui n'a pas été effectué.

Les trois VM originales sont laissées éteintes après export. La procédure
décrit la remise des trois archives et leur réimportation avec vérification des
MAC, du réseau interne et du port hôte 8080. Les clés privées d'administration
restent sur le poste ; les invités contiennent uniquement les données fictives
et les secrets générés pour cette démonstration.

Le [relevé final](etat-final-etape10.json) atteste les snapshots, les VM éteintes
et la topologie finale. Les RAM, vCPU, MAC et interfaces des trois OVA ont été
comparés aux VM originales : les configurations exportées sont conformes.
