# Étape 8 — Réseau et adressage

## Plan retenu

Le réseau applicatif est le réseau **interne VirtualBox `intnet-app`**, sur
`10.10.10.0/24`. Ce segment n'a ni passerelle ni serveur DHCP.

| Machine | Adaptateur 1 — interne | Adaptateur 2 | Accès depuis l'hôte |
| --- | --- | --- | --- |
| vm-proxy | 10.10.10.10/24 | NAT, adresse obtenue par DHCP | 127.0.0.1:8080 → port 80 |
| vm-metier | 10.10.10.20/24 | Désactivé | Aucun accès direct |
| vm-donnees | 10.10.10.30/24 | Désactivé | Aucun accès direct |

Toutes les VM utilisent l'adaptateur 1 pour le réseau interne ; le proxy ajoute
le NAT sur l'adaptateur 2. Les interfaces Linux sont identifiées par comparaison
des MAC fournies par VirtualBox avec `ip -j link show` dans chaque VM.
Les noms relevés sont conservés dans [interfaces-etape8.json](../docs/interfaces-etape8.json).

[plan.json](plan.json) définit le réseau et les adresses. Le script génère depuis
ce plan et les interfaces réellement observées les trois fichiers Netplan :

- [vm-proxy.yaml](vm-proxy.yaml)
- [vm-metier.yaml](vm-metier.yaml)
- [vm-donnees.yaml](vm-donnees.yaml)

Ces fichiers sont installés dans `/etc/netplan/50-cloud-init.yaml`, avec les
permissions `0600`. La configuration précédente est sauvegardée dans
`/var/backups/intern-etape8-netplan/`. Cloud-init reste désactivé comme à l'étape 7,
afin de conserver les noms des machines et leur configuration réseau.

## Exécution reproductible

Depuis la racine du dépôt, définir `VM_WORK` vers le répertoire local contenant
les VM et leur clé d'administration. Exemple :

```bash
export VM_WORK="$HOME/VMs-intern"
python3 deploiement/scripts/reseau_etape8.py "$VM_WORK"
```

Prérequis : trois clones de l'étape 7 éteints, adaptateur 1 en NAT de préparation,
adaptateur 2 désactivé, aucune redirection existante, clé et clés hôtes SSH de
l'étape 7 disponibles. Les ports locaux 2221–2223 et 8080 doivent être libres.
Le script refuse un état initial différent ; il ne restaure ni ne remplace les VM.

Le script effectue dans l'ordre :

1. Snapshot **`avant reseau`** sur chaque machine.
2. Accès SSH locaux temporaires, démarrage et relevé des interfaces par MAC.
3. Sauvegarde et installation du Netplan, validation avec `netplan generate`.
4. Arrêt propre, passage de l'adaptateur 1 en réseau interne, NAT conservé
   uniquement sur l'adaptateur 2 du proxy et redirection HTTP configurée.
5. Redémarrage des trois VM, lecture des adresses et routes, puis six pings :
   chaque machine vers les deux autres.
6. Arrêt propre des VM, retrait de la redirection SSH de vérification du proxy,
   puis lecture et contrôle de la topologie VirtualBox finale.

L'accès SSH de contrôle aux VM privées passe par le proxy (`ProxyJump`) avec la
clé détenue par l'hôte. Aucune clé privée n'est copiée dans les VM. L'hôte n'est
pas raccordé directement au réseau interne.

Pour refaire seulement les contrôles sur une topologie déjà configurée,
réactiver temporairement l'accès SSH du proxy comme indiqué plus bas, puis lancer :

```bash
python3 deploiement/scripts/reseau_etape8.py "$VM_WORK" --verifier
```

Ce mode ne réinstalle pas le réseau ; il compare les fichiers installés aux
fichiers livrés, effectue les tests, arrête les VM et retire l'accès SSH temporaire.

Si l'exécution s'interrompt, lire le message et inspecter l'état des VM avant
de reprendre les commandes nécessaires. Le snapshot `avant reseau` permet de
revenir à l'état initial après avoir arrêté la machine ; ne pas le restaurer
si des changements ultérieurs doivent être conservés.

## Vérifications et preuves

Les sorties suivantes sont enregistrées après le redémarrage sur la topologie cible :

```bash
hostname
ip -br address
ip route
sudo netplan get
ping -c 2 -W 2 10.10.10.20  # exemple depuis vm-proxy
ping -c 2 -W 2 10.10.10.30  # exemple depuis vm-proxy
```

Le script contrôle également que les VM métier et données n'ont aucune route
IPv4 par défaut, que seul le proxy conserve un NAT et que sa seule redirection
finale est `127.0.0.1:8080 → 80`.

Voir le [rapport](../docs/etape8.md) et les
[sorties réelles](../docs/preuves-etape8.txt). Les VM sont éteintes à la fin.
Le port HTTP est configuré pour le futur serveur web ; une réponse applicative
n'est attendue qu'après le déploiement de l'étape 9.

## Installation des paquets à l'étape suivante

Le choix retenu est **isoler puis ouvrir ponctuellement**. Pour les machines
métier et données, un NAT pourra être ajouté pendant la préparation des paquets
et dépendances, puis retiré avant les vérifications. Ne pas laisser ces accès
actifs dans la topologie finale. Aucune couche applicative n'est installée à
l'étape 8.

Pour rouvrir une session de maintenance après cette étape, ajouter temporairement
la redirection SSH sur l'adaptateur 2 du proxy, démarrer les trois VM, puis utiliser
le fichier SSH généré dans le répertoire local des VM :

```bash
VBoxManage modifyvm vm-proxy --natpf2 'ssh-verification,tcp,127.0.0.1,2221,,22'
for vm in vm-proxy vm-metier vm-donnees; do
  VBoxManage startvm "$vm" --type headless
done
(cd "$VM_WORK/access" && ssh -F ssh-etape8-interne.conf vm-metier)
```

Après les travaux, arrêter les machines privées puis le proxy et retirer cette
redirection avec `VBoxManage modifyvm vm-proxy --natpf2 delete ssh-verification`.

Références : [Netplan — exemples de configuration](https://github.com/canonical/netplan/blob/main/doc/examples.md),
[VirtualBox — commandes réseau](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/vboxmanage.html).
