# Étape 10 — Vérifier, mesurer et exporter

## Prérequis

Les trois VM doivent être installées selon la
[procédure de déploiement](DEPLOIEMENT.md) et fonctionner sur `intnet-app`.
Utiliser le même répertoire local des VM, avec ses fichiers SSH de l'étape 8.
Exécuter les commandes depuis la racine d'Intern, sur le poste VirtualBox,
sans `sudo`. Les scripts gèrent l'accès SSH temporaire du proxy et le retirent
après leurs opérations. Aucun adaptateur NAT n'est ajouté aux VM privées.

Sur la configuration mesurée, le proxy utilise le fournisseur de
paravirtualisation **`minimal`**, les deux autres VM conservent `default`
(effectivement KVM). Une tentative avec le proxy en KVM s'est bloquée pendant
le démarrage du noyau et n'a pas répondu dans les 240 secondes ; elle est
consignée séparément dans le rapport et exclue des médianes obtenues avec
la configuration corrigée. Pour reproduire ce réglage, proxy éteint :

```bash
VBoxManage modifyvm vm-proxy --paravirtprovider minimal
```

## Matrice et mesures

```bash
export VM_WORK="$HOME/VMs-intern"
python3 deploiement/scripts/verifier_etape10.py "$VM_WORK"
```

Le script prend sur chaque machine un snapshot **« avant verification »**,
machines éteintes, s'il n'existe pas déjà. Il contrôle les neuf liaisons de la
matrice avec `socket.create_connection`, délai maximal de deux secondes.
Les trois accès interdits doivent échouer ; toute liaison inattendue interrompt
la recette. Il relève également `ss -tlnp`, les routes et les services actifs,
puis exécute `SELECT 1` depuis le métier avec le compte applicatif.

La matrice testée est la suivante :

| Depuis | Proxy :80 | Métier :8000 | Base :5432 |
| --- | --- | --- | --- |
| Hôte | Oui, via 127.0.0.1:8080 | Refusé | Refusé |
| vm-proxy | — | Oui | Refusé |
| vm-metier | Oui | — | Oui |
| vm-donnees | Oui | Oui | — |

Le protocole comporte **trois séries**, sur la même configuration :

1. Arrêt propre des trois VM ; attente de l'état `poweroff`.
2. Chronométrage monotone avant le premier `startvm`, puis démarrage dans
   l'ordre données, métier, proxy. Arrêt du chronomètre au premier HTTP 200
   contenant un catalogue non vide sur `http://127.0.0.1:8080/api/v1/offers/`.
   Le sondage a un intervalle de 0,5 s et un délai HTTP maximal de 5 s.
3. Confirmation des accès SSH, puis trente secondes au repos.
4. Lecture côté hôte de `VmRSS` dans `/proc/<pid>/status` des trois processus
   VirtualBox identifiés par UUID, et somme en octets.
5. Somme des tailles des fichiers VDI/VMDK/VHD des trois clones, avec leurs
   snapshots. Lecture séparée de `st_size` et de `st_blocks × 512`.
6. Dix GET séquentiels sur la même route de consultation. Chaque mesure inclut
   la connexion HTTP, le transfert complet et la lecture JSON. Le client urllib
   n'utilise ni session authentifiée ni cache HTTP ni connexion persistante.

La médiane des trois séries est retenue pour chaque grandeur. Pour la latence,
on retient d'abord la médiane des dix appels de chaque série, puis la médiane
de ces trois valeurs. Les trente valeurs brutes restent disponibles.

La mémoire RSS peut compter plusieurs fois des pages partagées ; elle ne
représente ni la RAM configurée des invités ni une différence de mémoire globale
du poste. Le modèle, VBoxSVC et les autres applications ne sont pas comptés.
Le disque inclut l'historique des snapshots des trois clones, mais exclut le
modèle, les ISO et les OVA. Les démarrages partent de VM éteintes, sans purge
du cache disque hôte. Il s'agit de références au repos, pas d'un essai de charge.
Pour comparer aux conteneurs, conserver la route, le jeu fictif, le client HTTP,
les trois séries et les dix appels ; documenter les différences de mesure mémoire
et l'absence éventuelle de snapshots côté conteneurs.

Résultats générés : [matrice brute](docs/joignabilite-etape10.json),
[sorties des vérifications](docs/preuves-etape10.txt) et
[configuration, valeurs brutes et médianes](docs/mesures-etape10.json).

## Exports OVA

Prévoir suffisamment d'espace libre hors du dépôt. Le script arrête proprement
les machines encore en marche, retire l'accès SSH temporaire et exige la
topologie finale avant d'exporter.

```bash
python3 deploiement/scripts/exporter_etape10.py "$VM_WORK"
(cd "$VM_WORK/exports-etape10" && sha256sum -c SHA256SUMS)
```

Les trois fichiers `vm-proxy.ova`, `vm-metier.ova` et `vm-donnees.ova`, ainsi
que `SHA256SUMS`, sont créés sous **`$VM_WORK/exports-etape10`**.
Le script refuse d'écraser des OVA existants. Chaque export utilise
`VBoxManage export --ovf20 --manifest` ; les empreintes de tous les fichiers
OVF et VMDK sont contrôlées directement dans l'archive. VirtualBox lit également
chaque appliance avec `VBoxManage import --dry-run`.

Si une exécution a été interrompue après la création d'une archive complète,
`--reprendre` contrôle les archives existantes et exporte uniquement celles qui
manquent. Une archive incomplète ou dont le manifeste est invalide est refusée :
examiner ce fichier avant une nouvelle tentative, sans écraser un export valide.

Ces contrôles attestent la création, l'intégrité et la lecture des exports ;
ils ne sont pas un essai de démarrage après réimportation. Les OVA représentent
l'état courant installé ; ils ne conservent pas l'arbre des snapshots.
Les trois archives sont à remettre ensemble avec leur fichier de sommes.
Elles contiennent les comptes fictifs et les secrets de cette démonstration.
La clé SSH privée d'administration reste sur le poste, hors des invités.

Les [empreintes et tailles](docs/exports-etape10.json) et les
[sorties des exports](docs/preuves-exports-etape10.txt) restent dans le dépôt.
Les VM originales sont laissées éteintes après export.

## Réimporter sur un poste de consultation

Utiliser des noms libres et un répertoire hors du dépôt. Sur un poste neuf,
les noms d'origine peuvent être conservés. Sur le poste de préparation,
ne pas remplacer les trois VM existantes. Exemple de lecture préalable :

```bash
VBoxManage import "$VM_WORK/exports-etape10/vm-proxy.ova" --dry-run
```

Après importation réelle, vérifier les ressources, le réseau interne commun et
les adresses MAC. Les configurations Netplan utilisent les MAC des cartes :
sur un poste neuf, conserver les MAC avec `--options keepallmacs` ou adapter
les trois fichiers Netplan avant de démarrer les services. Une seconde copie
ne doit pas partager le réseau `intnet-app` avec les VM originales : les adresses
IP seraient identiques. Vérifier également que le port hôte 8080 est libre.

Sur un poste neuf, après vérification de `SHA256SUMS`, importer et démarrer :

```bash
for vm in vm-donnees vm-metier vm-proxy; do
  VBoxManage import "$VM_WORK/exports-etape10/$vm.ova" \
    --options keepallmacs --basefolder "$VM_WORK/machines-importees"
done
for vm in vm-donnees vm-metier vm-proxy; do
  VBoxManage startvm "$vm" --type headless
done
curl -f http://127.0.0.1:8080/health/ready/
```

Attendre le démarrage des services avant le dernier contrôle. Consulter ensuite
`http://127.0.0.1:8080/login`. Ce scénario de réimportation est une procédure
fournie ; il n'est pas compté parmi les vérifications exécutées sur les exports.

Référence des options d'export/import :
[documentation Oracle VirtualBox](https://docs.oracle.com/en/virtualization/virtualbox/7.1/user/vboxmanage.html).

Le [rapport de résultats](docs/etape10.md) rassemble les relevés réellement obtenus.
