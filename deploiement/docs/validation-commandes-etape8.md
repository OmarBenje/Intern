# Contrôle des commandes de l’étape 8

Exécution réelle le 16 octobre 2026, sur les trois VM existantes avec
VirtualBox `7.2.8_RPMFUSIONr173730`.

| Commande ou contrôle | Résultat observé |
| --- | --- |
| `bash outils/executer_etape.sh 8` | Réussite, code 0. Trois VM conservées et éteintes ; réseau interne `intnet-app`, NAT uniquement sur le proxy. |
| `bash outils/executer_etape.sh 8 verifier` | Échec avant les contrôles réseau : SSH vers `vm-donnees` indisponible après 240 s. Le proxy répond et peut joindre la VM données par ping, mais la connexion au port SSH est fermée. |
| Essai avec paravirtualisation `minimal` sur les deux VM privées | Même échec SSH. Cet essai ne permet pas d’attribuer la panne au réglage de paravirtualisation. |
| Tests ciblés du lanceur et des transitions VirtualBox | 21 tests réussis, avec outils simulés, dont un SSH volontairement bloqué. |

La gestion de `showvminfo` réessaie les erreurs temporaires de session, y
compris les sorties partielles avec `VMState="stopping"` et les erreurs
`VBOX_E_INVALID_OBJECT_STATE`. Les erreurs permanentes restent signalées.
L’attente SSH vérifie le proxy avant les VM privées ; un processus SSH bloqué
et ses sous-processus sont limités par un délai réel.

Les nouvelles preuves de topologie ne sont pas validées par cette exécution.
La cause du refus SSH à l’intérieur des VM privées reste à diagnostiquer.
Les preuves réseau déjà livrées proviennent d’une autre exécution.

Journaux locaux, ignorés par Git, dans `.execution/` :
`verification-commande8.log`, `verification-commande8-verifier.log`,
`verification-commande8-verifier-minimal.log` et `ssh-vm-donnees.log`.

## Défaut observé dans le système invité

La console de `vm-metier`, capturée pendant le diagnostic, affiche :
`EXT4-fs error (device sda1): htree_dirblock_to_tree`,
`Directory block failed checksum`, `Aborting journal on device sda1-8`
et `Remounting filesystem read-only`.
Son arrêt propre n’a pas été confirmé dans les 120 secondes prévues.
Ce défaut nécessite un diagnostic du système de fichiers invité avant une
validation complète. La cause du défaut EXT4 et celle du refus SSH de
`vm-donnees` ne sont pas établies par ces observations.
La capture locale est `.execution/vm-metier-diagnostic.png`.
Aucune réparation de système de fichiers n’a été lancée pendant ce contrôle.

## État laissé après le contrôle

| VM | État | Paravirtualisation |
| --- | --- | --- |
| `vm-donnees` | Éteinte ; réglage précédent restauré | `default` |
| `vm-metier` | En pause pour conserver son état après le défaut EXT4 | `minimal` (essai encore appliqué) |
| `vm-proxy` | Éteinte ; accès SSH temporaire retiré | `minimal` (réglage préexistant) |

La valeur précédente de `vm-metier` était `default` ; elle est enregistrée
avec celle de la VM données dans
`.execution/paravirtualisation-avant-verification8.json`.
La remise en état du disque et le retour au réglage précédent nécessitent
une intervention distincte sur cette VM. Aucune coupure forcée n’a été effectuée.
Le nettoyage du proxy a effectivement rencontré une erreur transitoire de
session VirtualBox : la nouvelle attente l’a réessayée et l’arrêt a abouti.
