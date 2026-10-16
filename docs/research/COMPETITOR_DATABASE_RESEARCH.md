# Recherche concurrentielle pour le modèle de données d’Intern

Recherche effectuée le **28 septembre 2026**. Périmètre : Simplify et Tsenta, concurrents directs ; Teal et Huntr, références complémentaires pour les CV, documents et le suivi des candidatures. Dix-neuf sources primaires retenues, accessibles publiquement, sans connexion à un compte ni exploration d’API privée.

## Ce que cette recherche permet d’affirmer

Les concurrents documentent leurs fonctions et certaines catégories de données, rarement leur architecture interne. Aucun schéma SQL, jeu de migrations, index ou modèle d’isolation des utilisateurs n’a été trouvé dans les sources consultées. **Les entités proposées ici constituent une conception pour Intern, pas une reproduction prétendument exacte des bases concurrentes.**

Trois niveaux sont employés : **attesté** = fonction déclarée dans une documentation officielle ; **documenté** = champ, catégorie de données ou technologie explicitement nommé ; **inférence** = choix de modélisation recommandé pour satisfaire ces comportements. Une déclaration de l’éditeur n’est pas un test indépendant du produit. Une absence dans ce corpus ne démontre pas l’absence d’une fonction.

## Matrice concurrentielle

| Acteur | Fonctions attestées | Données explicitement documentées | Apport pour Intern |
|---|---|---|---|
| Simplify | Profil commun, recommandations, autofill, tracker, Autopilot en bêta. [S1](https://help.simplify.jobs/articles/0738509-signing-up-for-simplify), [S5](https://help.simplify.jobs/en/help/articles/1784339-getting-started-with-autopilot) | Parcours, formation, compétences, préférences ; CV multiples et réponses réutilisables. [S1](https://help.simplify.jobs/articles/0738509-signing-up-for-simplify), [S2](https://help.simplify.jobs/articles/2415391-using-copilot-to-autofill-applications) | Profil structuré partagé par découverte, génération et candidature ; distinguer autofill et exécution autonome. |
| Tsenta | Recherche, préparation, soumission, suivi ; validation avant envoi configurable. [S7](https://tsenta.com/), [S9](https://tsenta.com/changelog) | Reçu de candidature, réponses, documents, confirmations ; PostgreSQL managé et Firebase Authentication déclarés. [S7](https://tsenta.com/), [S8](https://tsenta.com/privacy) | Un dossier de candidature et des exécutions asynchrones séparés ; preuve de ce qui a été envoyé. |
| Teal | Tracker, suivi des étapes, CV lié à chaque candidature. [S11](https://help.tealhq.com/en/articles/14435727-how-to-track-your-job-applications) | Description complète, dates, salaire, notes, contacts, enthousiasme, version du CV. [S11](https://help.tealhq.com/en/articles/14435727-how-to-track-your-job-applications) | Conserver les documents et l’offre tels qu’utilisés au moment de la candidature. |
| Huntr | Tableaux configurables, activités, dossiers de candidature et export. [S13](https://help.huntr.co/en/articles/13413245-the-job-board), [S16](https://help.huntr.co/en/articles/14367332-application-hub-and-packets), [S17](https://help.huntr.co/en/articles/11757717-download-export-your-board) | Étapes, événements, offres reçues, contacts, documents. [S14](https://help.huntr.co/en/articles/10042702-activities), [S15](https://help.huntr.co/en/articles/12640406-understanding-the-job-card) | Le suivi exige un historique métier et des objets liés, au-delà d’une colonne `status`. |

## Simplify : le profil comme référence commune

**S1 — Profil.** L’inscription peut analyser un CV pour initialiser formation, expérience et compétences. L’utilisateur peut aussi construire le profil manuellement ; rôles visés, lieux et préférences salariales personnalisent l’expérience. [Documentation d’inscription](https://help.simplify.jobs/articles/0738509-signing-up-for-simplify).

**Inférence Intern :** modéliser séparément identité, expériences, études, compétences et préférences. L’import doit produire des propositions de données avec leur provenance ; un nouveau CV ne devrait pas écraser silencieusement des corrections manuelles. Le document importé et les faits du profil ont des cycles de vie distincts.

**S2 — Autofill.** Copilot permet de choisir entre plusieurs CV. Les réponses écrites aux questions particulières sont mémorisées et réutilisées lorsque la question exacte revient. Le candidat vérifie et soumet lui-même dans ce mode. [Guide Copilot](https://help.simplify.jobs/articles/2415391-using-copilot-to-autofill-applications).

**Inférence Intern :** séparer bibliothèque de réponses et réponses d’une candidature. Stocker question originale, langue, contexte entreprise/offre, source et date de validation. Une similarité sémantique ne suffit pas à autoriser la réutilisation d’une réponse : une même formulation peut demander des faits dépendant de l’employeur.

**S3 — Tracker.** Il accepte les offres externes et les ajouts manuels avant candidature. L’import CSV exige entreprise et intitulé, avec lieu facultatif. Le guide décrit statut, filtres enregistrés, favoris, archive réversible et suppression distincte. [Guide du tracker](https://help.simplify.jobs/en/articles/2140179-using-the-job-tracker).

**Inférence Intern :** un intérêt sauvegardé n’est pas une soumission. Un dossier privé doit pouvoir exister sans offre déjà référencée dans le catalogue global. `archived_at`, statut de recrutement et date de soumission doivent rester indépendants.

**S4 — Collecte.** La politique décrit les champs/options/valeurs des formulaires et un cache local du profil, du CV et des réponses récentes. Elle distingue informations volontaires d’auto-identification, matching recruteur et données d’extension. Pour Gmail, elle annonce stockage des métadonnées et aperçus, pas du corps complet ni des pièces jointes. [Politique, mise à jour le 19 août 2026](https://simplify.jobs/privacy).

**Inférence Intern :** classifier les données et leur finalité ; conserver un minimum de métadonnées pour l’email ; ne jamais diffuser des réponses sensibles dans les logs, le catalogue ou le matching. La copie locale d’extension doit avoir une stratégie d’expiration et de purge.

**S5 — Agent autonome.** Autopilot est annoncé en bêta pour certains membres Simplify+. Il soumet les offres choisies, sans revue finale ; une réponse incertaine entraîne un échec sans consommation de crédit. Les questions interactives avec reprise et la candidature planifiée aux matchs sont présentées comme futures. [Guide Autopilot](https://help.simplify.jobs/en/help/articles/1784339-getting-started-with-autopilot).

**Inférence Intern :** enregistrer le mode autorisé, la configuration utilisée et le motif d’arrêt. La consommation d’un crédit doit dépendre d’un résultat défini, pas du démarrage d’un worker. Prévoir les états d’attente sans les confondre avec des fonctions concurrentes déjà disponibles.

**S6 — Découverte.** Job Matches et Job Board exposent la même base d’offres ; les matchs sont une sélection quotidienne utilisant profil, préférences, CV, compétences et autorisation de travail. [Matches et Job Board](https://help.simplify.jobs/en/help/articles/6542018-job-matches-vs-job-board).

**Inférence Intern :** une recommandation relie candidat et offre existante ; elle ne duplique pas l’offre. Son score et son explication doivent porter une version de calcul et la date du profil évalué.

## Tsenta : exécuter, faire valider, conserver un reçu

**S7 — Parcours.** Le site décrit une file de candidatures, des échecs et des besoins d’intervention. Il annonce un reçu pouvant contenir champs envoyés, réponses libres, CV, lettre et confirmation ; les préférences incluent lieu, salaire, expérience et famille de métier. [Présentation officielle](https://tsenta.com/).

**Inférence Intern :** distinguer `application` (dossier), `application_run` (tentative technique) et `submission` (envoi confirmé). Le reçu doit référencer les versions exactes des documents et réponses. Une absence de confirmation après un clic ne doit pas déclencher automatiquement un second envoi.

**S8 — Technologie et intégrations.** La politique nomme Fly.io avec PostgreSQL managé, Firebase Authentication, Anthropic/OpenAI, PostHog/Sentry et Dodo Payments. Elle décrit OAuth, révocation des jetons et journaux de connecteur comportant nom d’outil, dates et client OAuth. Elle décrit également la conservation des messages synchronisés après déconnexion. **Incohérence documentaire :** la section 1(c) limite l’email aux OTP temporaires, tandis que les sections 4(c), 5 et 6 décrivent classification et stockage de messages liés à l’emploi. [Politique effective au 24 août 2026](https://tsenta.com/privacy).

**Inférence Intern :** PostgreSQL est un choix compatible avec ce domaine, mais cette source ne prouve aucune table particulière. Séparer identité applicative et fournisseur d’authentification ; jetons chiffrés/références de coffre, autorisations révocables, audit sans secrets, synchronisation idempotente et politique explicite après déconnexion. Ne pas copier une politique de conservation contradictoire.

**S9 — Validation.** Le changelog du 1er juillet 2026 introduit la revue et l’édition avant soumission. Il précise que le mode auto-approve demeure disponible. [Changelog Tsenta](https://tsenta.com/changelog).

**Inférence Intern :** conserver une autorisation explicite liée à une version du dossier. Modifier ensuite une réponse ou un document invalide cette validation. Les modes manuel, validation préalable et automatique doivent être des données auditables.

**S10 — MCP.** Tsenta publie un point d’entrée MCP HTTP et une connexion OAuth avec jeton de courte durée renouvelable. [Guide MCP](https://tsenta.com/mcp).

**Inférence Intern :** les actions web, extension ou assistant doivent passer par la même logique métier. Prévoir origine de commande, identifiant d’idempotence et permissions de l’intégration ; ne pas donner au connecteur un accès direct aux tables.

## Teal : mémoire de la recherche et contexte relationnel

**S11 — Suivi.** Teal documente conservation de la description complète, étapes jusqu’à l’acceptation, dates de sauvegarde/candidature/relance, notes, contacts, enthousiasme et association au CV utilisé. Il propose aussi un export du tracker. [Guide daté du 27 juillet 2026](https://help.tealhq.com/en/articles/14435727-how-to-track-your-job-applications).

**Inférence Intern :** conserver un snapshot d’offre même si la page source disparaît ; lier le CV envoyé à une version immuable. Les notes et contacts sont privés au candidat, y compris quand l’entreprise appartient au catalogue partagé.

**S12 — Données connectées.** La politique cite contenu de carrière, descriptions, notes et suivi. Elle décrit des connexions Google facultatives pour contacts et calendrier en lecture seule ; la déconnexion arrête les accès futurs sans effacer automatiquement les données importées. [Politique du 12 août 2026](https://www.tealhq.com/privacy-policy).

**Inférence Intern :** différencier révocation d’accès, suppression de l’import et suppression du compte. Pour une extension future réseau/calendrier, conserver fournisseur, identifiant externe, propriétaire, date de synchronisation et liens aux dossiers sans rendre les contacts globaux.

## Huntr : événements, documents et workflow personnalisable

**S13 — Tableaux.** Huntr permet de choisir tableau et liste à l’ajout d’un poste ; les listes standard peuvent être renommées, ajoutées et réordonnées. [The Job Board, 30 avril 2026](https://help.huntr.co/en/articles/13413245-the-job-board).

**Inférence Intern :** si les colonnes deviennent personnalisables, les dissocier des statuts métier stables. Une colonne « entretien technique » peut correspondre à la même phase canonique qu’« entretien RH », sans casser les statistiques.

**S14 — Activités.** Une activité peut être liée à un poste ou être générale. Elle possède catégorie, dates, notes et état de réalisation. Les changements de certaines étapes créent automatiquement des activités. [Activities, 11 juillet 2025](https://help.huntr.co/en/articles/10042702-activities).

**Inférence Intern :** séparer tâches à faire et événements accomplis. Un historique horodaté permet les métriques ; `updated_at` ne permet pas de reconstruire un délai de réponse. Identifier la source automatique/manuelle évite de compter deux fois le même événement.

**S15 — Fiche.** La documentation liste URL source, lieu, salaire, échéance, description ; les entretiens ont date/heure/format et notes ; une offre reçue peut comporter rémunération, avantages, début et conditions. [Job Card, 24 octobre 2025](https://help.huntr.co/en/articles/12640406-understanding-the-job-card).

**Inférence Intern :** entretiens et propositions d’embauche méritent des entités propres avec cardinalité multiple par dossier. Une candidature peut comporter plusieurs tours et plusieurs versions d’offre reçue ; le salaire du poste publié n’est pas celui finalement proposé.

**S16 — Dossier de documents.** Un Application Packet regroupe CV adapté depuis un CV de base, lettre et modèle de relance. Supprimer le packet conserve le poste ; supprimer le poste supprime son packet. [Application Hub and Packets, 1er mai 2026](https://help.huntr.co/en/articles/14367332-application-hub-and-packets).

**Inférence Intern :** la filiation des documents et leurs liens au dossier doivent être explicites. Choisir les règles de suppression par relation ; un `CASCADE` global risquerait d’effacer un CV source partagé par plusieurs dossiers.

**S17 — Portabilité.** L’export complet comporte plusieurs CSV classés par type : jobs, activités, profil, contacts. L’export des métriques expose notamment titre, entreprise, date de création, liste et source. [Download/Export Your Board, 12 novembre 2025](https://help.huntr.co/en/articles/11757717-download-export-your-board).

**Inférence Intern :** préparer un export utilisateur cohérent sur toutes ses données, avec identifiants de liaison et version de format. La structure CSV confirme des domaines de données, sans révéler la structure physique de leur stockage.

**S18 — Contacts.** Un contact peut être lié à plusieurs postes et exister dans le carnet général du tableau. [Guide officiel Managing Contacts](https://guides.huntr.co/Managing-Contacts-81a28d867dac4d2c824e94deb64ffd2e?pvs=25).

**Inférence Intern :** relation plusieurs-à-plusieurs entre contacts privés et dossiers de candidature ; éviter une seule colonne `recruiter_email` dans la candidature.

**S19 — Partage.** La politique décrit partage de profil avec consentement, rattachement à une organisation et partage des données d’un tableau avec un autre utilisateur. [Politique Huntr](https://api.huntr.co/privacy).

**Inférence Intern :** ne pas confondre compte individuel et organisation cliente. Le partage/coaching pourra s’ajouter avec autorisations explicites par ressource ; il ne justifie pas d’exposer par défaut toutes les candidatures à un recruteur.

## Traduction en exigences d’architecture pour Intern

Les points suivants sont des **recommandations de conception**, issues des comportements précédents ; ils ne constituent pas des faits sur les implémentations internes concurrentes.

| Domaine | Objets nécessaires | Invariant important | Motivation |
|---|---|---|---|
| Identité et confidentialité | Utilisateur, profil, préférences, autorisations | Toutes les données privées ont un propriétaire vérifié | S1, S4, S8, S12, S19 |
| Catalogue | Entreprise, offre, source, identifiant externe, snapshot | Ne pas confondre offre publique et dossier privé | S3, S6, S11 |
| Documents | Document, version, fichier, filiation, association à candidature | Une soumission conserve sa version envoyée | S2, S7, S11, S16 |
| Candidature | Dossier, statut de recrutement, événements, soumission | Sauvegardé ≠ envoyé ; archive ≠ rejet | S3, S7, S14 |
| Agent | Exécution, étapes, tentative, intervention, autorisation, reçu | Retry technique ≠ nouvelle candidature ; validation liée au contenu | S5, S7, S9 |
| Formulaires | Question, option, réponse réutilisable, réponse soumise | Contexte et provenance des réponses conservés | S2, S4 |
| Suivi | Contact, relation contact-dossier, note, tâche, entretien, offre reçue | Plusieurs contacts/entretiens/offres par dossier | S11, S14, S15, S18 |
| IA | Génération, entrée référencée, version modèle/prompt, résultat, validation | Résultat calculé distinct de la vérité du profil | S1, S2, S6, S9 |
| Connecteurs | Connexion, permissions, secret référencé, curseur, événement importé | Déconnexion et suppression sont deux opérations distinctes | S8, S10, S12 |
| Facturation | Droit d’usage, mouvement de crédit, référence événement | Débit atomique et idempotent au résultat facturable | S5 |
| Exploitation | Audit, export, demande de suppression, politique de conservation | Pas de secrets ni réponses sensibles dans les logs | S4, S8, S17 |

Priorité de réalisation : catalogue et profil, documents versionnés, dossier et historique, puis orchestration et reçus. Contacts/suivi approfondi, email, intégrations MCP et tableaux personnalisables peuvent être activés progressivement ; leur présence dans le benchmark ne les rend pas tous indispensables au premier lancement.

## Limites et arbitrages à retenir

1. **Schémas internes inconnus.** PostgreSQL est explicitement déclaré par Tsenta ; aucune affirmation équivalente n’est établie ici pour Simplify, Teal ou Huntr. Aucune preuve ne permet de déduire ORM, tables, cardinalités physiques, index, sharding, RLS ou architecture de queues.
2. **Sources évolutives.** Les dates relatives de certains guides Simplify diffèrent entre résultat de recherche et page ouverte. Elles restent des dates relatives observées, pas des dates exactes recalculées. Les conditions de bêta doivent être revérifiées avant comparaison commerciale.
3. **Fonctions à distinguer.** Simplify documente séparément Copilot et Autopilot ; Tsenta documente validation préalable et auto-approve. L’architecture Intern doit représenter le niveau d’autonomie autorisé sans le déduire du nom commercial d’une fonction.
4. **Conservation à définir pour Intern.** Les politiques concurrentes servent à repérer des catégories et opérations ; elles ne constituent ni une politique juridique réutilisable ni une justification pour collecter toutes ces données.
5. **Pas de benchmark de performance.** Les volumes, taux de succès et vitesses marketing ne sont pas repris comme preuves de dimensionnement. Celui-ci doit partir du trafic attendu d’Intern, de la fréquence des imports et de la durée réelle des exécutions.
