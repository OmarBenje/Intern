# Vérification réelle du guide — 16 octobre 2026

## Réparation et remise à zéro

La VM `vm-metier`, UUID `83ebf4fc-e538-40fa-94ca-99c166a456ca`, était
inaccessible parce que `vm-metier.vbox` manquait. La copie `.vbox-prev`
était lisible et tous les disques référencés existaient. Le fichier a été
récupéré et la VM réenregistrée sans suppression de disque.

Les trois VM étaient arrêtées. Leurs états ont été sauvegardés en snapshots
`archive-*`, puis les snapshots `base propre` ont été restaurés.
Le fournisseur de paravirtualisation `minimal` a été appliqué aux trois VM.
La liste VirtualBox ne contient plus de VM inaccessible.

Commande réutilisable depuis Intern, lorsque les VM sont arrêtées :

```bash
python3 outils/reinitialiser_vm.py --base-propre
```

## Résultats déjà obtenus

| Commande | Résultat réel |
| --- | --- |
| `bash outils/preparer_vm.sh` et `VBoxManage list vms` | Réussite ; quatre VM accessibles, dont le modèle. |
| `bash outils/executer_etape.sh 8` | Réussite ; six pings, adresses et routes vérifiées, VM éteintes, SSH temporaire retiré. |
| `bash outils/executer_etape.sh 9` | Réussite après reprise ; PostgreSQL, Django et Nginx actifs, réponse HTTP prête. |
| `bash outils/executer_etape.sh 10` | Consultation des preuves livrées réussie ; aucune nouvelle mesure avec cette commande. |
| `bash outils/executer_etape.sh 10 demarrer` | Réussite. |
| `bash outils/executer_etape.sh 10 mesurer` | Interrompue proprement à la demande utilisateur ; aucun nouvel export validé. |
| `bash outils/executer_etape.sh 11` | Réussite sur Docker Engine ; PostgreSQL sain, quatre offres. |
| `bash outils/executer_etape.sh 12` | Réussite ; métier sain, HTTP prêt, image de 372 903 397 octets. |
| `bash outils/executer_etape.sh 16` | Lecture du rapport livré réussie. |
| `bash outils/executer_etape.sh 17` | Vérification des preuves livrées réussie ; il ne s'agit pas d'une nouvelle campagne. |
| `bash outils/executer_etape.sh 18` | Statistiques et courbes recalculées ; PDF de quatre pages A4, douze empreintes SHA-256 correctes. |

La vérification de l'installation de JMeter a révélé une erreur : le lanceur
ajoutait un nom de fichier à un manifeste SHA-512 qui en contenait déjà un.
Le traitement est corrigé ; l'archive officielle téléchargée passe sa vérification.
L'exécutable de cette session est dans
`.execution/jmeter/apache-jmeter-5.6.3/bin/jmeter`.

Les 40 tests automatisés des outils passent, dont cinq tests de remise à zéro
et un test de téléchargement JMeter couvrant deux formats de manifeste ainsi
que le refus d'une empreinte incorrecte. Ces tests restent distincts des essais réels.

## Arrêt et point de reprise

L'automatisation a été arrêtée à la demande de l'utilisateur pendant la mesure
de l'étape 10. Le vérificateur a reçu une interruption et a exécuté son nettoyage ;
le pilote et son groupe de processus ont ensuite été arrêtés. Les trois VM
restent allumées. Les anciens exports ont été remis dans
`../.local-vms/exports-etape10`, leur emplacement initial.

Le dernier point validé est l'étape 9, ainsi que `10 demarrer`.
Reprendre manuellement à l'étape 10 dans `EXECUTION.md`.
La nouvelle campagne de l'étape 17 n'a pas été lancée.

Depuis Intern, état et journaux de cette exécution :

```bash
cat .execution/validation-20261016/progression.json
cat .execution/validation-20261016/journal.jsonl
tail -n 40 .execution/validation-20261016/enchainement.log
```

Chaque commande écrit aussi son propre fichier `etape*.log` dans ce dossier.
Le parcours automatique ne continue plus en arrière-plan.
Une nouvelle campagne demanderait environ 3 h 45, plus préparation et transitions.
L'analyse 18 du guide utilise explicitement les preuves canoniques ; la nouvelle
campagne reste séparée et reçoit sa propre vérification.

Les deux cas JMeter GUI ont été exécutés séparément dans la vraie interface,
pilotée par ses actions Swing. Le cas correct donne trois HTTP 200 ; le cas
incorrect donne CSRF 200 puis connexion 401, sans consultation ultérieure.
Les JTL, captures du rendu Swing et assertions sont conservés dans
`mesure/resultats/validation-gui-20261016/`. Les captures du bureau par Robot
renvoyaient une image noire sous Wayland et ne sont pas retenues.

Un premier `8 verifier` a échoué pendant l'échange initial SSH. Une reprise
bornée des seules expirations de bannière a été ajoutée ; le nouvel essai a réussi.
Un premier déploiement 9 a ensuite expiré pendant `netplan apply` : son délai
est passé de 30 à 120 secondes, puis le déploiement a été repris dans son état
existant. Ces échecs restent dans les journaux privés de la session.

La machine subit une forte charge de fond, notamment l'indexation
de VS Code ; les mesures nouvelles doivent être interprétées dans ce contexte.
La priorité des trois énumérations de fichiers VS Code identifiées a été abaissée
de nice 0 à nice 10 pendant la reprise du déploiement.
Les états archivés des VM restent comptabilisés dans leur occupation disque.
