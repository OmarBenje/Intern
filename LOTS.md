# Moteur de stages européens — lots d'implémentation

Périmètre autorisé le 30 septembre 2026 : implémenter [la spec](docs/moteur/INTERNSHIP_ENGINE_SPEC.md) et ajouter son bilan de livraison à la fin du document. Le découpage ci-dessous reprend son périmètre ; les fichiers applicatifs préexistants sans rapport sont conservés.

## Lot 1 — Schéma et collecte mutualisée

Modèles additifs, révisions de sources, Greenhouse/Ashby/Lever, registre de sources, planificateur et consommateur dédié. Backoff, leases, confirmation des disparitions et quarantaine des snapshots anormaux. Tests transactionnels et imports reproductibles.

deps: -

## Lot 2 — Qualité et matching expliqué

Extraction multilingue déterministe avec preuves, classification des stages, géographie européenne et contraintes. Matching séparant compatibilité, contradiction et inconnues. Déduplication prudente et tests des faux amis ; pas d'IA simulée.

deps: 1

## Lot 3 — API et fonctionnalités candidat

Catalogue public, filtres, recherches sauvegardées, feedback, exclusions d'entreprises, signalements, notifications internes et couverture. Imports de liens privés avec accès réseau borné. Préserver les contrats de candidature, reçus, confidentialité et suppression/export des données.

deps: 1,2

## Lot 4 — Intégration, vérification et documentation

Vérifier les parcours API réels, migrations, workers et non-régression. Documenter commandes, activation des sources et limites. Compléter la fin de la spec avec résultats observés ; séparer code livré et objectifs de couverture/qualité nécessitant un corpus et une exploitation réelle.

deps: 1,2,3

Les contrats de modèles permettent de travailler sur les modules des lots 2 et 3 en parallèle de leur socle ; leur intégration et leur recette restent dépendantes des lots précédents. Aucun merge ni déploiement distant n'est inclus dans cette exécution locale.

## Lot 5 — Extension des collecteurs et résilience par annonce

Personio/Recruitee, registre étendu, snapshots partiels avec diagnostics durables. Une erreur de détail SmartRecruiters n'empêche plus les autres offres valides d'être importées ; un lot partiel ne ferme aucune offre absente. Filtrage stage + Europe inchangé.

deps: 1,2

## Lot 6 — Découverte récurrente et flux transversaux

Requêtes persistées, curseurs, provenance, erreurs et couverture effective. Flux publics Arbeitnow et JobSearch Suède ; résolution des liens de carrière vers des boards connus ou candidats non supportés. Activation bornée après import pilote, worker et commandes d'exploitation.

deps: 5

## Lot 7 — Portails publics Workday

Connecteur de carrière public par employeur, configuration explicitement vérifiée, pagination et limites. Données de contrat et pays conservées ; snapshots partiels en cas de détail défaillant. Pas d'accès aux APIs privées du recruteur.

deps: 5

## Lot 8 — Recette de couverture réelle

Sauvegarde, migrations additives, tests métier, découverte et imports réels multi-domaines. Vérifier le catalogue servi au frontend, rapporter les nouveaux pays/sources/stages et les sources bloquées. Exécuter effectivement les cycles de découverte et mise à jour, puis consigner les limites dans la spec.

deps: 5,6,7

Extension explicitement autorisée par « implémente » après présentation de la section 13 bis. Les agents travaillent sur des fichiers attribués dans le checkout courant pour préserver le pilote non commité et les modifications d'autres tâches.

## Lot 9 — Couverture Europe V2 : portails RMK

Spec : `docs/moteur/couverture/EUROPE_COVERAGE_V2_SPEC.md`. Connecteur public SuccessFactors RMK pour
SAP, Schaeffler et ZF, reconnaissance des sources, import partiel sûr et worker.
Livré localement : +79 stages, 920 offres dans 21 pays ; 272 tests backend passent.
Les connecteurs et flux nationaux restants sont explicités dans la spec.

deps: 5,6,8

## Lot 10 — Couverture Europe V3 : iCIMS et Taleo

Spec : `docs/moteur/couverture/EUROPE_COVERAGE_V3_SPEC.md`. Deux connecteurs publics sur cinq portails
inspectés, intégrés à la découverte et au worker. Livraison locale : +8 stages,
928 offres dans 21 pays ; 282 tests backend passent. Snapshots partiels sûrs,
contrôles de pays, contrat, identité et expiration ; aucune migration nécessaire.

deps: 5,6,9

## Lot 11 — JobSpy et registre de portails

Spec : `docs/moteur/couverture/EUROPE_COVERAGE_V4_SPEC.md`. Imports publics directs, worker de
requêtes, curseurs, snapshots partiels et inventaires épinglés. Pilote LinkedIn :
53 stages supplémentaires ; 1 000 candidats employeurs enregistrés. 295 tests
backend passent sur PostgreSQL isolé. Validation Docker interrompue par une erreur
I/O du moteur ; état d'exploitation distinct du code testé.

deps: 5,6,10

## Lot 12 — Teamtailor, Workable et récupération des stages bilingues

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V5_SPEC.md`.
Deux connecteurs publics, registre étendu, pilotes et snapshots partiels.
Reconnaissance titre anglais / description française ; correction des attributs
HTML sans valeur qui interrompaient la découverte LinkedIn. Suite : 304 tests.
Résultats : `docs/research/2026-09-30-v5-results.json` et rapports pilotes V5.
EURES, WTTJ, Eightfold et import direct des sources nationales restent à traiter.

## Lot 13 — Import direct EURES

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V6_SPEC.md`.
Connecteur recherche + détails, qualification textuelle obligatoire en plus du
code contrat EURES, reprises et leases persistés, worker et service Compose dédiés.
315 tests backend. Pilote contrôlé : 13 stages publiables sur 41 annonces.
31 pays configurés ; les pages restantes sont collectées progressivement.
WTTJ, Eightfold et import direct des sources nationales restent à traiter.

## Lot 14 — Welcome to the Jungle

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V7_SPEC.md`.
Index public, qualification stricte, résumés source explicitement étiquetés,
partition temporelle contre le plafond de pagination, worker et Compose dédiés.
320 tests backend passent. Pilote : 111 stages publiables sur 208 annonces.
47 pays configurés, collecte progressive. Eightfold et import direct des sources
nationales restent à traiter.

## Lot 15 — Eightfold PCSX

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V8_SPEC.md`.
Portails inspectés, recherche multilingue, fiches complètes, filtrage européen,
import partiel et ordonnanceur existant. 326 tests backend passent.
Pilotes : NVIDIA 3 stages, Dolby 3. Microsoft suspendu après limitation de débit.
SmartApply et les autres tenants ne sont pas annoncés comme supportés.
Prochain chantier : import direct des sources nationales.

## Lot 16 — JobTech / Platsbanken, Suède

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V9_SPEC.md`.
Import direct recherche + détails complets, quatre termes suédois/anglais,
taxonomie pays vérifiée, corroboration suédoise, expiration automatique et reprise
persistée. Pilote : 76 résultats examinés, 24 offres JobTech distinctes publiables
après contrôle du télétravail. Pages restantes collectées progressivement.
Worker local activé ; service Compose configuré, image non reconstruite.
Bundesagentur, France Travail et NAV restent à traiter.

## Lot 17 — Bundesagentur / Allemagne

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V10_SPEC.md`.
Recherche publique v6 et fiches v4, qualification textuelle stricte malgré la
catégorie partagée Praktikum/Trainee, lieux vérifiés, dates de publication et
reprise durable. 346 tests backend passent. Pilote : 49 fiches publiables sur
60 résultats, 11 incertains. Trois requêtes configurées ; collecte continue locale
activée. Les volumes source ne sont pas des ajouts uniques tous fournisseurs.
Service Compose configuré sans reconstruction d’image dans ce lot.
France Travail et NAV restent à traiter.

## Lot 18 — Couverture observée et déduplication

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V11_SPEC.md`. Page `/engine` avec chiffres
publiables par pays/source, pagination, erreurs, suspensions et déduplication.
Audit JSON reproductible via `audit_coverage`. Rapprochement conservateur par
liens normalisés + contenu et lieux identiques, fusion réversible existante.
Scan réel : zéro candidat répondant à toutes les preuves ; aucune fusion forcée.
Deux recherches Bundesagentur débloquées (références contenant un point),
reprise observée aux pages suivantes. 353 tests backend passent, build frontend
et 2 tests navigateur desktop/mobile/erreur passent. Collectes partielles et
limitations de débit restent visibles, sans promesse d’exhaustivité.

## Lot 19 — Reprise des collectes existantes

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V12_SPEC.md`.
WTTJ : slug avec point accepté et reprise réelle 50 résultats/39 imports, page 10.
SmartRecruiters : changement de total et répétition d’ID donnent un snapshot
partiel ; essai réel encore limité par un timeout réseau. Indeed : erreurs HTTP
identifiées au lieu de faux résultats vides ; accès amont toujours en échec.
LinkedIn : cooldown partagé d’au moins une heure, sans contournement.
360 tests backend passent. Workers locaux relancés ; filtres stage/Europe inchangés.

## Lot 20 — NAV / Arbeidsplassen, Norvège

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V13_SPEC.md`. Flux officiel incrémental,
jeton public expérimental ou `NAV_FEED_TOKEN`, curseur de page + offset, retrait
des annonces inactives et expiration norvégienne. Worker NAV local lancé et
service Compose configuré (image non reconstruite). Départ de rattrapage sur
184 jours, puis surveillance du flux. 367 tests backend passent, build frontend
et configuration Compose valides. Pilote : 1000 événements, 1 stage importé à
Bergen. La recherche de la page initiale a rencontré des timeouts ; reprise
vérifiée depuis un identifiant de page obtenu en direct. Pas d’exhaustivité prouvée.

## Lot 21 — Activation ciblée des entreprises ATS

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V14_SPEC.md`. Commande bornée
`activate_ats_candidates` : prévisualisation, imports explicites, rapport par
source et pause sans rendement cible. 13 pilotes, 3 sources maintenues : Deloitte
Netherlands, Cabify et Picnic. 48 nouvelles fiches visibles sur ces sources après
contrôle, dont 37 aux Pays-Bas/Espagne ; pas de gain IT/GB/IE confirmé. Dix sources
suspendues. Sept faux positifs événementiels Deloitte retirés avec rules-8.
374 tests backend passent, services locaux sains et collecteurs relancés.
Rapports initiaux et vérifiés conservés ; aucune fusion automatique ni promesse
de stages uniques entre plateformes.

## Lot 22 — Audit du rappel et récupération Celonis

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V15_SPEC.md`. Dix sources revérifiées en
réseau. Activation fondée sur les pays qualifiés, y compris un pays explicite
dans le libellé du lieu. Le classificateur reconnaît les titres Intern corroborés par
`As a … Intern` dans la description. Celonis réactivé : dix fiches visibles,
dont quatre nouvellement qualifiées et six déjà présentes à maintenir fraîches.
Le bilan initial du lot 21 sous-comptait ses pays GB/ES. Aucun gain IT/IE confirmé.
54 tests ciblés passent ; rapports avant/après conservés et collecteurs relancés.
Suite complète réessayée : 408/410 réussis, deux erreurs hors périmètre dans
WorkflowConcurrencyTests sur `Company.logo_source_url` obligatoire.

## Lot 23 — File persistante de vérification ATS

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V16_SPEC.md`. File AtsProbe avec admission
bornée, bail de reprise, retry des sources vides à sept jours et backoff erreurs.
Activation sur toute l'Europe ; bilan visible dans /engine. Pilote de 100 :
95 sans stage confirmé, 5 erreurs, aucune nouvelle offre. Neuf anciennes sources
vides inscrites pour revérification, total 109. Worker local actif ; service
Compose configuré sans rebuild. 21 tests ciblés, build et 2 tests navigateur
passent. Le prochain travail de couverture devra améliorer la sélection des
candidats, le pilote séquentiel actuel n'ayant apporté aucun stage supplémentaire.

## Lot 24 — Sources guidées par les stages existants

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V17_SPEC.md`. Liens ATS des offres fraîches,
puis correspondance exacte des noms avec le registre épinglé, provenance
conservée et exclusion des sources connues. 50 pistes testées : 20 actives,
27 sans résultat confirmé, 2 erreurs, 1 conflit d'identité mis à l'écart.
262 nouvelles fiches visibles après contrôle, doublons entre plateformes possibles.
Portail groupe Richemont correctement libellé ; artefactjobs ambigu désactivé.
29 tests ciblés passent, worker relancé. Commandes de découverte et traitement
ciblé disponibles dans le runbook ; aucune promesse d'exhaustivité.

## Lot 25 — Déduplication ciblée des 262 fiches

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V18_SPEC.md`. Fusion réversible autorisée
par lien spécifique commun, employeur/titre/lieux compatibles, sources fraîches
et empreintes revalidées. Les descriptions peuvent différer ; contenu et lien
employeur privilégiés, actualisations conservées après fusion. Audit réel :
262 fiches, 26 groupes de titres à approfondir, aucune fusion certaine ; zéro
fusion exécutée. 35 tests ciblés passent. Ne pas présenter les fiches ajoutées
au lot 24 comme des stages uniques prouvés.

## Lot 26 — Résolution publique des liens et références

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V19_SPEC.md`. Résolution bornée des groupes
ambigus, attribution JSON-LD stricte, preuves persistantes avec expiration et
invalidation lors des changements de source. 61 sources examinées : 31 identités
ATS déjà connues, 20 bloquées, 10 sans preuve attribuable. Aucun nouveau lien
employeur confirmé ; réaudit des 262 fiches : zéro fusion, 26 groupes toujours
ambigus. 42 tests ciblés passent. Rapports conservés, aucune unicité revendiquée.

## Lot 27 — Admission ATS priorisée par couverture européenne

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V20_SPEC.md`. Classement commun à tous les
connecteurs par couverture du pays témoin, un nouveau portail par employeur et
budget porté à 100. Pilote complet : 50 actifs, 34 en attente, 16 erreurs.
520 nouvelles fiches publiables dans 17 pays après 18 exclusions motivées ;
doublons interplateformes toujours possibles. Apports notamment IT 20, NL 12,
IE 4 ; FR reste majoritaire (344). 17 tests ciblés passent, rapports avant/après
et preuves conservés. Restent les contrats ATS mal renseignés et les facettes
Workday indisponibles, sans assouplissement des critères stage/Europe.

## Lot 28 — Contrats ATS corroborés et revue des incertitudes

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V21_SPEC.md`. rules-17 exige une confirmation
textuelle du contrat ATS, distingue contrats contradictoires et perspectives
d'embauche, reconnaît alternants, ambassadeurs étudiants et événements.
Motifs et extraits conservés ; vue d'administration de revue en lecture seule.
15 726 fiches réauditées : 26 anciennement publiées passent en attente
(19 sans corroboration, 5 stage/alternance, 2 contradictions). Les 18 masquages
du lot 27 restent en place ; les 34 vrais stages du corpus restent confirmés.
50 tests backend, un test navigateur et build passent. Collecteurs relancés,
backend sain. Rapports intermédiaire et final conservés, sans suppression de fiches.

## Lot 29 — Workday : facettes personnalisées et secours borné

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V22_SPEC.md`. Paramètres pays reconnus par
libellé explicite, secours global limité à 2000 annonces et toujours partiel.
Vérification stage/Europe sur les détails inchangée ; 429 interrompt la collecte
en préservant Retry-After, y compris après pagination. Onze pistes traitées :
7 actives, 3 en attente, 1 homonyme écarté (CS / C&S Wholesale Grocers).
68 nouvelles fiches visibles dans 11 pays, dont GB 40 et FR 13 ; doublons
interplateformes possibles. 38 tests ciblés passent, rapports conservés.

## Lot 30 — Nouveaux employeurs par recherche publique indépendante

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V23_SPEC.md`. Manifeste de pistes revues,
prévisualisation puis admission bornée à 100, provenance datée et contrôles
identité/portail/pays ; réutilisation des probes sans réinitialiser leur backoff.
Pilote sur FI/GR/CZ/BG/RO : 8 portails testés, 5 actifs, 3 en attente.
114 nouvelles fiches dans 11 pays, dont CZ 7, GR 5 et RO 1 ; aucun gain FI/BG.
Recherche web encore éditoriale ; imports récurrents sur les portails activés.
24 tests ciblés passent, lint/Django/readiness vérifiés. Rapports conservés,
sans promesse d'exhaustivité ni d'unicité des fiches.

## Lot 31 — Récupération ciblée des trois portails en attente

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V24_SPEC.md`. Diagnostic public : Plum ne
liste plus le stage indexé, Gen liste deux stages en Malaisie, Civitta masque les
pays du poste derrière un lieu générique. Fallback Lever limité à une déclaration
explicite de pays du poste, preuve conservée, pays structuré prioritaire et remote
préservé. Une nouvelle fiche Civitta, disponible notamment dans 19 pays européens,
sans copies par pays. Plum/Gen gardent leur reprise prévue. 48 tests passent,
rapports et fixture conservés ; aucune fusion, workers rechargés, readiness 200.

## Lot 32 — Audit par source et rappel de stages confirmés

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V25_SPEC.md`. Commande d'audit en lecture
seule : compteurs par source, fraîcheur, exclusions, incertitudes, diagnostics
d'import et limites de comptage. 1615 boards activés en configuration audités.
Trois corrections : pays principal Lever, métadonnée de villes Greenhouse,
corroboration des stages danois (rules-18). Imports réels Winamax/Qube/WPP :
23 fiches nouvellement visibles (2/4/17), catalogue 8134 → 8157. Trois groupes
possiblement dupliqués, aucune fusion certaine. 68 tests ciblés et build passent.

## Lot 33 — Stages signalés Sentry / Microsoft

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V26_SPEC.md`. Admission Sentry et correction
Ashby : workplaceType prioritaire sur isRemote. Quatre fiches rendues visibles :
Sentry AT, Back Market FR, Enpal DE, Kognity SE. Collecteur Eightfold espacé de
2 secondes ; Microsoft réactivé après son backoff, une fiche Belgique importée.
Le détail du stage Microsoft Bucarest (1970393557007677) reste limité par HTTP429 :
non importé, reprise planifiée. Total attribuable : 5 fiches, pas une couverture
exhaustive. 24 tests ciblés distincts passent ; lint/diff/readiness vérifiés.

## Lot 34 — Reprise persistante des collectes Eightfold

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V27_SPEC.md`. Migration 0030 : progression
par portail, recherches/pages et détails restants, validée et expirant à 24 h.
Offres et progression atomiques sous bail, Retry-After conservé sur résultat
partiel ; aucune fermeture par absence. Audit expose progression et échéance.
Pilote réel : Microsoft Bucarest 1970393557007677 récupéré, fiche 16126 visible
(RO). Son identité a été adoptée du diagnostic de l'import précédent pour amorcer
la reprise, sans avancer next_run_at. La recherche suivante reçoit encore 429.
NVIDIA : 2 fiches relues, reprise conservée après 429 ; Dolby : 3 fiches relues,
parcours terminé. Aucun nouveau stage pour ces deux employeurs. Gain total : une
fiche Microsoft. 38 tests passent, schéma cohérent, readiness 200. La reprise
persistante reste limitée à Eightfold ; pas de promesse d'exhaustivité.

## Lot 35 — Collecte supervisée et files correctement mesurées

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V28_SPEC.md`. Correction du diagnostic :
les échéances des sources synthétiques ne sont pas des travaux ATS dus. Nouvelle
commande collection_status, séparation imports/maintenance, superviseur local
à neuf rôles avec verrou et redémarrage progressif, services Compose séparés et
restart policies. Aucun backoff fournisseur réduit ; un worker par rôle.

Pilote local : imports ATS prêts 116 → 101 entre 17:10:25 et 17:12:08 Paris.
EURES 30 → 27, WTTJ 46 → 43, Jobtech 1 → 0, NAV 1 → 0. Les files évoluent
également avec les nouvelles échéances et les erreurs ; pas de traduction de ces
chiffres en nouvelles offres. Bundesagentur conserve des erreurs de réponse et
LinkedIn des limitations. Neuf processus actifs, verrou exclusif vérifié en réel,
532 tests passent, Compose valide et backend HTTP200. Fenêtre courte : débit
soutenu sur 24 h non démontré. Superviseur à relancer après redémarrage du PC.

## Lot 36 — Découverte automatique de nouveaux employeurs

Spécification : `docs/moteur/couverture/EUROPE_COVERAGE_V29_SPEC.md`. Admission automatique depuis
les liens structurés des flux publics et le registre ats-scrapers épinglé déjà
importé. Concordance stricte nom/portail, provenance durable, conflits et sources
connues exclus, pauses/backoffs conservés. Quota partagé de 50 admissions/jour UTC,
500 pistes/passage, curseur transactionnel. Maintenance supervisée → AtsProbe →
validation publique → import des stages européens. L'ancienne activation des
flux exclut désormais les candidats déjà confiés aux sondes.

Pilote automatique : 50 nouveaux portails mis en file ; deux examinés à 17:29:57
Paris, sans stage européen confirmé, zéro nouvelle offre à cet instant. La file
continue sans intervention. 63 tests ciblés passent, lint et diff propres. Les
alias, liens indirects et nouveaux employeurs absents des entrées actuelles
restent hors de ce mécanisme ; aucune promesse de recherche web exhaustive.

## Lot 37 — Déduplication par contenu
- Spec : [EUROPE_COVERAGE_V30_SPEC.md](docs/moteur/couverture/EUROPE_COVERAGE_V30_SPEC.md).
- Passe maintenance : copies exactes ou quasi identiques, entreprise/titre/lieux
  compatibles, garde-fous sur références, chiffres et historiques privés.
- Cas Joko vérifié : offres 37, 16163 et 16303 rattachées à 1, quatre sources
  conservées, Ads Creative distincte. Résumés/full text rapprochés après revue.
