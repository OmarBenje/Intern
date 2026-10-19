# Incidents des campagnes de capacité

Ce registre concerne les campagnes de mesure, pas la maintenance de production
décrite dans [MAINTENANCE.md](../deploiement/MAINTENANCE.md). Les anciens résultats restent
inchangés : une correction du code ne transforme pas un essai interrompu en
mesure validée. Les identifiants ci-dessous correspondent aux dossiers de
`mesure/resultats/` et de `../.execution-campagnes/`.

## Incidents réellement observés

| ID | Campagne et symptôme | Cause établie ou limite du diagnostic | Correction et prévention | Vérification reproductible |
|---|---|---|---|---|
| INC-01 | `capacite-20261018-101502-9055`, arrêt injecteur à 80 | Un maximum CPU ponctuel déclenchait le refus, sans distinguer une charge soutenue. | Moyenne pondérée sur 10 s ; conserver les pics bruts ; arrêter si la charge soutenue dépasse le seuil. Les anciens protocoles restent interprétés selon leur règle d’origine. | `test_short_cpu_spike_does_not_reject_a_new_campaign`, `test_sustained_injector_load_still_stops_the_campaign`, `test_cpu_window_weights_time_and_rejects_sampling_gaps` dans `tests/test_verifier_capacite.py`. |
| INC-02 | `capacite-20261018-111349-39983`, collecteur interrompu à 5 | Le processus Nginx surveillé avait disparu pendant une mise à jour automatique des VM. Les journaux système et APT ont identifié la mise à jour. | Suspendre les unités APT appartenant à la protection avant mesure, attendre une opération APT déjà engagée, figer les versions, puis restaurer la politique initiale. Ne jamais rattacher silencieusement le collecteur à un nouveau PID. | `test_disappeared_service_reports_the_monitored_pid`, `test_failed_collector_names_service_and_preserves_diagnostic` ; suite `deploiement/tests/test_maintenance.py`. |
| INC-03 | `capacite-20261018-120903-94499`, port 8081 occupé | Le proxy Docker de préparation essayait de publier le port encore réservé par la VM proxy. | Préparer uniquement PostgreSQL et l’API ; créer le proxy à l’arrêt pour copier les ressources ; ne démarrer le proxy Docker qu’après l’arrêt des VM. Refuser un propriétaire étranger du port avant de stopper les services. | `test_bootstrap_and_resume_do_not_publish_the_vm_measurement_port`, `test_foreign_port_owner_is_rejected_before_services_are_stopped`. Vérification réelle archivée dans `.execution/verification-bootstrap-sans-port.json`. |
| INC-04 | `capacite-20261018-122748-114362`, disponibilité refusée à 160 | 460 réponses enregistrées étaient HTTP 200, jusqu’à 4 753 ms ; le contrôle attendait 2 s. Les exceptions des trois contrôles n’étaient pas conservées : le motif exact de chacun ne peut pas être reconstruit. | Attendre 10 s comme JMeter ; conserver chaque tentative dans `disponibilite.jsonl` avec statut, durée et exception. Trois échecs consécutifs restent un arrêt de sécurité. Le seuil p95 acceptable reste 1 s sur le plateau. | `test_slow_success_within_jmeter_timeout_is_not_unavailability`, `test_three_timeouts_still_stop_and_preserve_diagnostic`, `test_http_failure_then_recovery_resets_counter`. |
| INC-05 | `capacite-20261018-133053-146630`, verrou occupé sans mesure active | `VBoxSVC` détenait le verrou hérité du descripteur Bash ; fermer seulement la copie du lanceur ne libérait pas le verrou. Identifié avec `lslocks` sur l’hôte. | Déverrouiller explicitement avant détachement du contrôleur et dans le traitement de sortie de préparation, également à l’étape 16. Conserver l’exclusion entre opérations réellement actives. | `test_preparation_releases_lock_even_when_daemon_inherits_descriptor` teste les étapes 16/17, succès/échec, avec un vrai processus fils conservant le descripteur. `test_operation_lock_excludes_parallel_measurement_and_maintenance` vérifie l’exclusion. |
| INC-06 | `capacite-20261018-133524-153667`, étalonnage interrompu à 140 | `calibration.log` indique `host_swapping` : le compteur passe de 0 à 239 pages alors qu’environ 8,2 Go sont disponibles. Ce signal de l’hôte ne démontre pas une limite du déploiement. | Garder la protection contre une activité swap pendant la charge. Propager le motif et le chemin du fichier de sécurité au manifeste, au journal et à l’erreur affichée, au lieu du seul message « Calibration failed ». | `test_calibration_reports_resource_guard_instead_of_generic_failure`, `test_memory_swap_oom_and_pressure_each_stop_escalation`. La stabilité de l’hôte reste une condition d’exécution, pas une propriété garantie par le code. |
| INC-07 | Même campagne, restauration déclarée incomplète | Pendant l’arrêt des VM, `showvminfo` échouait avec « The object is not ready », `E_ACCESSDENIED` et `COMGETTER(RemoteUSBDevices)`. | Réessayer ce cas transitoire précis, comme `VBOX_E_INVALID_OBJECT_STATE`, six fois au maximum. Ne pas réessayer indistinctement les vrais refus d’accès. Les restaurations Docker doivent continuer si celle des VM échoue. | `test_shutdown_usb_session_error_is_retried`, `test_real_access_denial_is_not_retried`, `test_persistent_virtualbox_lock_has_bounded_retries`, `test_vm_cleanup_error_does_not_skip_reference_or_hide_primary_error`. Vérification réelle ultérieure : `.execution/verification-restauration-capacite-20261018-133524-153667.json`. |
| INC-08 | `capacite-20261018-145712-196549`, arrêt mémoire dès le premier palier | Le fichier de sécurité indique `host_swapping`. La référence du contrôleur datait du début de sa préparation : elle pouvait inclure une activité antérieure à l’essai applicatif. Les relevés ne permettent pas d’attribuer précisément chaque page à une phase. | Reprendre les compteurs cumulés après l’étalonnage et son repos, juste avant chaque essai. Conserver la référence précédente dans le diagnostic et afficher le motif mémoire précis. Le pilote JMeter conserve son propre contrôle avant et pendant la charge. | `test_memory_counter_baseline_is_reset_after_calibration` et tests swap/OOM/pression mémoire. |
| INC-09 | `capacite-20261018-151501-212826`, `all predefined address pools have been fully subnetted` | Les anciens projets conservaient leurs réseaux après `compose stop` ; 12 réseaux de campagnes terminées ont été libérés. | À la fin d’une campagne de capacité immuable, utiliser `compose down` sans `--volumes`. Conserver volumes, snapshots, JTL et relevés. Les campagnes historiques reprenables gardent leur comportement `stop`. | `test_capacity_cleanup_releases_networks_without_removing_volumes`, `test_resumable_campaign_cleanup_keeps_containers_and_networks`. Vérification réelle : création puis suppression de deux nouveaux réseaux ; trace du nettoyage dans `.execution/nettoyage-reseaux-capacite.json`. |
| INC-10 | `capacite-20261018-155252-255979`, étalonnage arrêté à 1 utilisateur avec `host_swapping` | La règle stricte assimilait toute activité swap à une pression mémoire. Le relevé au moment de l’arrêt contient 8 670 937 088 octets disponibles, PSI 0 %, aucun OOM. Sur l’hôte, `swapon --show` identifie `/dev/zram0` ; aucune erreur de permission n’est signalée. | Nouveau protocole : `swap_avec_pression_uniquement: true`. Enregistrer le swap sans arrêt isolé ; maintenir l’arrêt pour mémoire insuffisante, PSI excessif et OOM, avec ou sans swap. Les anciens protocoles conservent leur règle stricte. Il s’agit d’un changement explicite du protocole, pas d’une modification rétroactive des preuves. | `test_swap_activity_without_pressure_does_not_abort_new_protocol`, `test_memory_pressure_without_swap_still_aborts`, `test_memory_swap_oom_and_pressure_each_stop_escalation`, `test_swap_pressure_policy_must_be_an_explicit_boolean`. Sources et portée dans `CAPACITE.md`. |

Les paliers 120 et 160 de `capacite-20261018-133524-153667` montrent respectivement
un p95 de 525 et 1 078 ms, sans erreur applicative. Le premier respecte le seuil,
le second le dépasse ; l’affinement avait donc commencé normalement. Une seule
série VM ne suffit pas à annoncer une capacité confirmée.

### Campagne du 18 octobre à 16 h 15

INC-11, `capacite-20261018-161522-278342` : 22 paliers sont conservés.
La série VM a affiné la borne acceptable à 150 utilisateurs (p95 947 ms), avec
un dépassement observé à 160 (1 094 ms). Ce sont des résultats exploratoires,
sans seconde série de confirmation. Sur Docker à 240, le garde-fou CPU observe
92,879 % d’un cœur sur une fenêtre de 10 s, contre un seuil de 80 %. La moyenne
JMeter du plateau est de 27,002 % d’un cœur et l’hôte ne dépasse pas 35,46 %
sur un relevé : l’arrêt est celui du protocole conservateur, sans démonstration
d’une saturation de tous les CPU. Le plateau Docker à 240 est également
incomplet : 169 utilisateurs observés et 71 échecs avant la fenêtre stable.
Il ne doit pas être présenté comme une mesure réussie à 240, ni le plateau à
320 (17 utilisateurs observés, 303 erreurs au total) comme une capacité validée.
Le seuil CPU n’est pas relevé après coup pour accepter ces résultats.
L’examen complémentaire du contrôle statique à 240 donne 8 731,3 requêtes
réussies/s, un plateau valide et une moyenne JMeter de 316,972 % d’un cœur.
JMeter utilise donc effectivement plusieurs cœurs ; le seuil applicatif de
80 % d’un cœur n’est pas un plafond physique établi. À 240 applicatif, la
hausse CPU se concentre autour des secondes 30–40 du plateau ; les moyennes
des tranches de 10 s des secondes 50–120 sont proches de 12–14 % d’un cœur.
Cela décrit un dépassement du seuil choisi, pas une saturation soutenue de
toute la machine. Le parcours statique ne contient pas les assertions Groovy
du parcours applicatif : sa marge ne valide pas à elle seule la marge du
générateur sur ce parcours. Une nouvelle règle CPU doit préciser les ressources
allouées à l’injecteur et être étalonnée avec un parcours représentatif avant
d’être utilisée pour une nouvelle campagne. Les bonnes pratiques Apache
[JMeter](https://jmeter.apache.org/usermanual/best-practices.html) recommandent
le mode CLI, la réduction des coûts inutiles et, au besoin, plusieurs moteurs ;
elles ne prescrivent pas ici notre seuil de 80 % d’un cœur.

INC-12, même campagne : `run()` documentait `TimeoutExpired` mais le remplaçait
par `RuntimeError`. La boucle de démarrage SSH ne pouvait donc plus reconnaître
ce dépassement de délai et réessayer. La restauration échouait après une seule
tentative, laissant la VM proxy occuper 8080 et empêchant le proxy Docker de
référence de redémarrer. Correction : conserver le type et l’objet de l’exception
après enregistrement du diagnostic. Test à travers la vraie chaîne
`boot_vm → ssh → run → subprocess.run`, en injectant seulement l’échec du
sous-processus : `test_real_command_timeout_still_reaches_ssh_boot_retry`.
Le test précédent simulait directement `ssh` et ne couvrait pas cette interaction.
`test_timeout_and_missing_executable_are_distinct_and_keep_diagnostics`
vérifie aussi la conservation du type et de l’objet de l’exception.

La restauration tente désormais l’arrêt ACPI même si la récupération SSH
échoue définitivement (`test_failed_ssh_recovery_still_attempts_acpi_shutdown`).
Un échec SSH peut encore empêcher de restaurer la politique APT : il reste
signalé, même si les VM ont pu être arrêtées et Docker rétabli. La récupération
réelle de cette campagne a restauré les trois politiques et les services de
référence sans rejouer les mesures. Les diagnostics initiaux sont conservés
dans `avant-recuperation/` sous le runtime ; les événements de récupération
s’ajoutent au journal. Les 22 paliers et le statut échoué restent conservés.
Le statut distingue désormais le diagnostic archivé antérieur à une restauration
confirmée de l’état courant (`test_restored_status_identifies_old_port_error_as_archived`).
La vérification sur l’hôte après récupération retrouve `rootlesskit` à l’écoute
sur 8080, le proxy `intern-docker-proxy-1` sain publiant ce port et aucune VM
active. Le message ancien « address already in use » reste conservé comme preuve.

### Audit complémentaire des journaux

Voir l’[audit détaillé de la campagne](AUDIT-capacite-20261018-161522-278342.md).
INC-13 : 71 délais à 240 et 303 à 320 étaient présents avant la récupération,
avec abandon des utilisateurs et plateaux incomplets. INC-14 : les journaux
Java partageant un nom par charge se remplaçaient ; un chemin privé unique
par exécution empêche désormais ces collisions. INC-15 : les journaux applicatifs
Docker n’étaient pas archivés avant suppression des conteneurs ; leur archivage
précède désormais le nettoyage et son échec ne bloque pas la restauration.
Les 32 journaux Java et les sorties des conteneurs déjà supprimés ne peuvent
pas être reconstruits par ces corrections. L’écart de versions Python est
également explicité dans l’audit sans mise à jour des VM pendant une mesure.

### Incident du test de validation

VAL-01 : le premier test réel de conservation du volume n’atteignait pas son
état prêt. La reproduction a établi une `PermissionError` : l’image applicative
s’exécute sans privilèges, alors que le volume temporaire neuf appartient à root.
La sonde de fichiers utilise maintenant explicitement `0:0` dans son seul
conteneur temporaire, sans modifier les utilisateurs des services Intern.
Le test reproduit d’abord ce défaut et vérifie son diagnostic, puis contrôle
le nettoyage et la conservation du fichier avec la sonde corrigée.
Le résultat réel est archivé dans
`.execution/verification-nettoyage-capacite.json`.

## Cas d’échec voisins couverts

| Situation | Comportement attendu | Tests principaux |
|---|---|---|
| Deux mesures, ou maintenance et mesure simultanées | Refus avant modification des déploiements ; aucun déverrouillage forcé d’une opération active. | `test_operation_lock_excludes_parallel_measurement_and_maintenance`, `test_campaign_lock_prevents_any_vm_change`. |
| Refus de verrou avant exécution | Afficher que la restauration est sans objet pour ce contrôleur, sans prétendre connaître l’état d’une autre opération. | `test_lock_refusal_does_not_claim_failed_restoration`. |
| Échec des prérequis avant détachement, ou contrôleur mort avant création du manifeste | Conserver un incident de précontrôle sans démarrer le contrôleur ; afficher les diagnostics d’un processus arrêté plutôt qu’une préparation indéfinie. | `test_preflight_failure_is_documented_before_detached_start`, `test_missing_manifest_does_not_claim_preparation_when_controller_has_exited`. |
| SSH indisponible ou lent au démarrage | Délai global borné ; réessayer un échec isolé ; diagnostic de la VM concernée. | `test_boot_waits_after_an_individual_ssh_timeout`, `test_hanging_ssh_readiness_has_a_real_deadline`. |
| SSH perdu pendant collecte | Interrompre l’essai si le collecteur se termine ; conserver ses journaux propres au palier ; arrêt VM par ACPI indépendant de SSH. | `test_new_collector_does_not_overwrite_previous_plateau_logs`, `test_shutdown_uses_acpi_without_ssh`. |
| Premier signal ACPI ignoré | Répéter la demande d’arrêt, avec une borne de 120 s ; ne pas couper brutalement une VM. | `test_acpi_is_repeated_if_guest_does_not_handle_first_request`. |
| Règle NAT équivalente existante | Réutiliser et préserver la règle ; refuser un conflit au lieu de remplacer une règle étrangère. | `test_equivalent_nat_rule_is_reused_regardless_of_name`, `test_incompatible_nat_target_or_wildcard_bind_is_rejected`, `test_boot_and_stop_preserve_borrowed_nat_rule`. |
| Projet, volume ou préparation sans provenance suffisante | Refuser avant arrêt des services ; conserver les ressources ; demander un nouveau runtime. | `test_conflict_fails_before_stopping_services_or_restoring_vms`, `test_volume_conflict_also_preserves_resources`, `test_owned_partial_preparation_can_resume_without_adopting_legacy_project`. |
| Protocole modifié, seuil non fini ou booléen | Refuser avant changement des déploiements ; ne pas mélanger les protocoles de mesure. | `test_nonfinite_or_boolean_thresholds_are_refused_before_any_deployment_change`, `test_historical_protocol_is_kept_with_its_original_hash`. |
| Relevé mémoire absent, non fini, négatif ou compteur cumulatif remis à zéro | Refuser de conclure à un hôte sûr ; signaler `invalid_host_memory_readings` ou `host_counters_reset`. | `test_invalid_or_reset_memory_counters_cannot_validate_host_safety`. |
| APT déjà actif, redémarrage requis, politique appartenant à une autre opération | Attendre ou refuser ; ne pas tuer APT/dpkg, ne pas restaurer la politique d’un autre propriétaire. | Suites `deploiement/tests/test_maintenance*.py`. |
| Seuil applicatif dépassé avec service disponible | Refuser le palier, affiner l’intervalle, conserver l’ordre des séries et les charges comparables. | `test_exploration_refines_and_confirms_without_replaying_above_breach`, `test_reverse_capacity_relationship_keeps_comparable_safe_levels`. |
| Plateau incomplet, repos insuffisant, divergence ou preuves altérées | Ne pas produire de capacité validée. | `test_missing_plateau_preserves_failure_and_request_errors`, suite `test_repos.py`, `test_divergent_repetitions_never_validate_capacity`, `test_full_raw_verification_and_tampering`. |
| Échec de commande, programme absent, dépassement de délai | Conserver commande, sortie standard, erreur, phase et code/type dans un fichier privé distinct. Les erreurs de restauration ne remplacent plus le diagnostic initial. | `test_failure_keeps_stdout_and_recovery_does_not_overwrite_first_diagnostic`, `test_timeout_and_missing_executable_are_distinct_and_keep_diagnostics`. |
| `SIGTERM`, `SIGINT`, commande `arreter` | Demander un arrêt coopératif ; terminer l’injecteur et les collecteurs ; tenter la restauration ; libérer le verrou. Les commandes déjà engagées restent bornées par leurs délais. | `test_real_sigterm_reaches_finally_and_releases_operation_lock`, `test_real_sigint_reaches_finally_and_releases_operation_lock`, `test_requested_stop_records_stopped_and_still_restores`, `test_failure_at_each_campaign_phase_always_attempts_restoration`. |
| Lecture du statut pendant une écriture | Remplacement atomique des JSON ; ignorer la dernière ligne de journal si elle est encore incomplète. | `test_failed_atomic_replace_preserves_previous_manifest_and_cleans_temporary_file`, `test_serialization_failure_cannot_truncate_previous_evidence`, `test_update_guard_status_uses_events_instead_of_assuming_activation`. |
| Disque plein ou stockage inaccessible pendant l’enregistrement d’un incident | Préserver le JSON précédent si son remplacement échoue ; afficher la cause initiale sur stderr et tenter quand même la restauration. L’écriture de nouvelles preuves reste impossible si aucun espace n’est disponible. | `test_full_diagnostic_disk_does_not_skip_restore_or_mask_initial_error`, tests atomiques de `test_incidents.py`. |

## Diagnostic de chaque nouvel incident

Pour chaque erreur interceptée par le contrôleur, `incident.json` dans les
résultats conserve la phase, la cause initiale, les liens vers les fichiers de
sécurité et les éventuelles erreurs de restauration. Le manifeste contient le
même résumé. Les commandes en échec ont chacune un fichier JSON privé sous
`command-errors/` dans le runtime. Le fichier `last-error.txt` reste un raccourci
de compatibilité ; il ne remplace pas cet historique. Les diagnostics privés
peuvent contenir des arguments sensibles : ne pas les copier dans un rapport
public sans les relire.

Pour une nouvelle erreur, conserver les résultats et relever : phase et charge,
cause initiale, contrôle ayant arrêté la campagne, état réel des services après
restauration, puis test reproduisant la cause avant correction. Ajouter une
ligne à ce registre quand une nouvelle catégorie de défaut est identifiée.
Ne pas modifier les seuils après coup pour rendre un essai acceptable.

```bash
bash outils/executer_etape.sh 17 statut
python3 -m unittest discover -s mesure/tests -v
python3 -m unittest discover -s deploiement/tests -v
python3 -m unittest discover -s outils -p 'test_*.py' -v
git diff --check
```

Le test Docker réel est explicite ; il n’est pas déclenché par la découverte
des tests unitaires. Il réserve le verrou partagé, utilise un projet aléatoire,
deux réseaux et un volume temporaires, puis les nettoie. Il ne démarre pas les VM :

```bash
python3 mesure/tests/integration_nettoyage_docker.py \
  --configuration ../.execution-campagnes/CAMPAGNE/configuration.json
```

## Portée des preuves et limites

Vérification avant INC-10 du 18 octobre 2026 : 87 tests de mesure, 26 tests de maintenance
et 56 tests des outils passent, soit **169 tests**. Les huit campagnes échouées
présentes ont une entrée dans le registre ; les 54 noms de tests cités existent
dans les suites. Le test Docker réel a confirmé la suppression des deux réseaux
et la conservation du fichier du volume. Après son nettoyage, aucun de ses
réseaux ou volumes temporaires ne reste et les trois services Docker de
référence sont toujours sains. `git diff --check` et la vérification de syntaxe
des lanceurs 16/17 passent également.

Les tests injectent des défaillances sans provoquer d’OOM réel, remplir le
disque, casser SSH ou interrompre APT sur les VM. Le test de signal utilise un
vrai sous-processus et celui du verrou de préparation un vrai fils conservant
le descripteur. Les vérifications Docker/VM réelles citées plus haut concernent
les états effectivement observés à leur date, pas tous les environnements.

Une coupure de courant, un `SIGKILL`, une panne du noyau, un Docker inaccessible
pendant la restauration ou la perte du disque peuvent empêcher tout nettoyage
automatique. Les verrous système disparaissent avec leurs processus, mais les
pauses APT persistantes et les ressources créées doivent alors être inspectées.
Ne pas supprimer un verrou ou un volume pour contourner le diagnostic.
La commande de maintenance autonome permet d’inspecter/restaurer la politique
APT après vérification du propriétaire ; voir [MAINTENANCE.md](../deploiement/MAINTENANCE.md).
La panne d’un service doit rester visible et invalider la mesure : le code ne
peut pas garantir l’absence de panne matérielle ou de perturbation de l’hôte.

INC-10 précise et remplace la prévention initiale d’INC-06 : le swap actif seul
reste bloquant uniquement pour les anciens protocoles stricts. Le changement
ne désactive pas les contrôles de mémoire disponible, PSI, OOM, CPU, erreurs
applicatives ou latence. La campagne interrompue n’est pas déclarée valide.

## INC-16 — CPU exprimé par cœur et course pendant l’arrêt ACPI

Campagne `capacite-20261018-195024-455892`, 23 paliers enregistrés. Le plateau
Docker de 200 utilisateurs contient 19 189 requêtes stables, zéro erreur,
p95 396 ms et 200 utilisateurs au plateau. L’injecteur atteint 82,3795 %
d’un cœur sur 10 secondes ; l’hôte atteint 30,0664 %. Le seuil de 80 %
appliqué à un seul cœur a interrompu la campagne sans démontrer une saturation
sur cet hôte de 12 cœurs. L’amendement de reprise explicite la capacité CPU
accessible, conserve les valeurs brutes et les protocoles antérieurs.

La restauration a subi un timeout SSH de démarrage, récupéré par la boucle
existante, puis un échec ACPI `Invalid machine state: Stopping` sur `vm-metier`.
L’état avait changé depuis sa lecture. Le contrôleur accepte désormais ce
refus uniquement si une nouvelle lecture confirme `stopping`, `poweroff` ou
`aborted` ; une VM encore `running` conserve l’erreur. L’attente d’arrêt reste
bornée à 120 secondes et n’utilise pas SSH.

Les journaux Java conservés de cette campagne ne contiennent aucune ligne
ERROR/WARN. Les trois archives Docker ne contiennent ni traceback, ni erreur
500 Django, ni FATAL/PANIC PostgreSQL, ni timeout upstream Nginx. Cela ne
supprime pas les échecs de parcours observés aux charges supérieures : Docker
240 et 320 comptent respectivement 50 et 300 erreurs, conservées dans les preuves.

Tests : course ACPI avec le véritable wrapper de commande ; refus conservé
si la VM reste allumée ; conversion CPU sans modification des unités hôte ni
règle historique ; refus d’une modification des seuils applicatifs ; conservation
du journal brut ; archivage du dernier palier ; refus d’un SQL modifié avant
mutation ; poursuite de l’affinement sans rejouer les faibles charges.
Voir [la procédure de reprise](CAPACITE.md#reprise-dune-campagne-interrompue-au-contrôle-de-linjecteur).

La reprise effective au palier Docker 200 a franchi le contrôle CPU et terminé
ses 120 secondes stables. Son plan JMeter possède la même empreinte que l’essai
archivé (`ddf7ab8a…`), et ses paramètres de scénario sont identiques. Cependant,
45 connexions et 147 lectures du parcours expirent à 10 secondes pendant la
montée : seuls 8 utilisateurs restent au plateau. Ce palier est donc rejeté,
malgré zéro erreur parmi les 896 requêtes stables restantes. La recherche
continue par affinement sous 200 ; cet essai n’est pas une capacité validée.

Les premières requêtes étaient déjà lentes avant l’interruption : CSRF moyen
3 011 ms et connexion moyenne 3 978 ms, contre 4 476 et 6 204 ms à la reprise.
Les deux workers API sont occupés pendant cette phase ; aucun OOM ni redémarrage
de worker n’a été observé dans les relevés inspectés. Cela localise les expirations
au démarrage du parcours sans établir à lui seul la cause de la différence entre
les sessions. L’interruption et la restauration de base sont explicitement
conservées dans la provenance ; les confirmations devront décider de la
reproductibilité du résultat.

## INC-17 — Faux départ d’utilisateur en bord de fenêtre d’étalonnage

`worker-vm-20261019-121536-124124` : arrêt après 5 paliers, lors de
l’étalonnage 180 utilisateurs de la seconde série avec 4 workers. Le débit
statique est suffisant et aucune requête n’échoue. Quatre requêtes de 5,386 à
5,550 s traversent la borne finale ; leur exclusion des statistiques stables
était prise à tort pour un départ des utilisateurs. Le message de débit
insuffisant était ambigu et le journal console des étalonnages était écrasé.

Correction versionnée du contrôle de présence, maximum brut et requêtes de bord
visibles, motifs précis, journaux distincts et deux tentatives au maximum avec
repos dans le comparatif de workers. Après deux refus, le bloc est écourté et
les autres blocs continuent ; les données refusées ne sont jamais validées.
Les arrêts de sécurité restent bloquants. Archivage des journaux systemd invités
avant restauration, sans empêcher celle-ci en cas d’échec d’archivage.

Audit, portée et preuves : [AUDIT-workers-vm-20261019.md](AUDIT-workers-vm-20261019.md).
Tests : `tests/test_worker_calibration.py` et
`test_exhausted_calibration_skips_load_and_continues_other_blocks` dans
`tests/test_workers.py`. Les preuves de la campagne échouée restent inchangées.
