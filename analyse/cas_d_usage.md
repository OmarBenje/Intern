# Intern : analyse fonctionnelle DEV

- **Auteurs :** Hicham et Omar
- **Établissement :** Polytech Marseille
- **Année universitaire :** 2026-2027

## 1. Besoin, périmètre et acteurs

Intern aide les candidats à rechercher des stages en Europe, préparer leur
profil et leur CV, puis suivre leurs candidatures. Le recruteur gère ses offres
et les candidatures qui lui ont été explicitement transmises. La démonstration
locale repose sur des données fictives et couvre ces échanges sans promettre
d'envoi vers un service externe.

| Acteur | Actions autorisées | Limites |
| --- | --- | --- |
| Candidat | Gérer son profil et ses CV, rechercher et enregistrer des stages, créer et suivre ses candidatures | Ses propres données ; transmission au recruteur seulement après candidature explicite |
| Recruteur | Vérifier son adresse et son entreprise, préparer et publier ses offres, examiner les candidatures reçues | Son espace personnel ; publication soumise à vérification ; aucun accès général aux profils candidats |
| Administrateur | Gérer les comptes, les entreprises, les offres, les sources et les référentiels ; vérifier les recruteurs | Accès réservé à l'administration ; les actions restent séparées des parcours candidat et recruteur |

Le candidat et le recruteur sont les deux profils de l'application.
L'administrateur assure la gestion et la supervision. Le choix candidat ou
recruteur à l'inscription ne permet jamais d'obtenir des privilèges
d'administration. Après connexion, le serveur détermine les droits depuis le compte.
Plusieurs recruteurs peuvent référencer la même entreprise sans partager leur
espace : l'entreprise commune ne suffit pas à autoriser l'accès aux offres privées.

## 2. Règles de gestion et matrice de traçabilité

| ID | Règle métier | Garantie attendue | Cas d'usage |
| --- | --- | --- | --- |
| R1 | Toute offre du catalogue appartient à une entreprise existante | Référence obligatoire et intégrité référentielle ; entreprise sans offre autorisée | UC03, UC07, UC10 |
| R2 | Les données privées restent accessibles à leur propriétaire ; une candidature explicite donne au recruteur destinataire accès aux seules données transmises | Relations de propriété en base et filtrage serveur par session, y compris pour le téléchargement du CV | UC04–UC06, UC07, UC08 |
| R3 | La source choisie pour candidater appartient à l'offre visée | Contrainte relationnelle et contrôle métier de cohérence | UC05 |
| R4 | Un candidat possède au plus un dossier par offre ; répéter une candidature directe ne la duplique pas | Unicité candidat/offre et traitement idempotent de la candidature directe | UC05, UC08 |
| R5 | Le login est unique et le mot de passe est haché avec sel et fonction lente | Unicité SQL, contrôle de l'e-mail et hachage serveur ; nom SQL explicite `mot_de_passe_hash` demandé par le manuel | UC01, UC02 |
| R6 | Un compte créé attend l'activation par l'administrateur avant connexion ; la publication recruteur exige aussi un e-mail et une entreprise vérifiés | État du compte, permissions serveur et contrôles de publication distincts | UC01, UC02, UC07, UC09, UC11 |

La base garantit l'intégrité des relations et les unicités ; le serveur connaît
la session et applique les autorisations. Une entreprise vérifiée ne remplace
pas l'activation du compte. Le choix d'un rôle dans le navigateur ne constitue
jamais une preuve d'autorisation.

## 3. Cas d'usage : déclencheur, parcours et erreurs

| ID / acteur | Déclencheur et enchaînement nominal | Erreurs et cas limites |
| --- | --- | --- |
| UC01 / candidat ou recruteur | Ouvrir l'inscription ; choisir son profil ; saisir identité, e-mail et mot de passe ; soumettre ; lire la confirmation d'attente | E-mail utilisé, mot de passe faible, champs manquants, adresse personnelle recruteur, privilèges injectés, CSRF absent, réseau indisponible ; aucune session avant activation |
| UC02 / candidat ou recruteur | Ouvrir la connexion ; saisir les identifiants ; serveur vérifie le mot de passe et l'état ; créer une session puis ouvrir le parcours du compte | Identifiant inconnu et mot de passe erroné : message commun ; compte inactif : message d'attente ou de désactivation ; session expirée : nouvelle connexion |
| UC03 / candidat | Ouvrir le catalogue ; rechercher et filtrer ; consulter une offre et son entreprise ; ajouter un favori | Aucun résultat : « Aucun stage ne correspond à votre recherche » ; offre indisponible : message explicite ; session absente : connexion requise pour les actions privées |
| UC04 / candidat | Ouvrir son profil ; compléter les champs ; téléverser un PDF ; sélectionner puis télécharger son CV | PDF invalide/trop volumineux ; profil incomplet : champs à compléter ; aucun CV : invitation à en ajouter ; document tiers refusé |
| UC05 / candidat | Depuis une offre, choisir la source ; créer son dossier ; pour une offre directe, confirmer les données transmises ; retrouver le suivi | Source d'une autre offre refusée ; doublon empêché ; candidature directe sans CV prêt refusée ; source fictive externe : aucun envoi réel |
| UC06 / candidat | Ouvrir le tableau de bord et ses candidatures ; consulter un dossier et ses événements ; se déconnecter | « Vous n'avez pas encore de candidature » ; identifiant tiers : ressource non divulguée ; après déconnexion : accès privé refusé |
| UC07 / recruteur | Ouvrir ses offres ; créer un brouillon ; compléter et prévisualiser ; publier une fois vérifié ; suspendre ou archiver | Publication sans vérification refusée ; offre d'un autre recruteur inaccessible même dans la même entreprise ; « Vous n'avez pas encore d'offre » |
| UC08 / recruteur | Ouvrir les candidatures reçues ; consulter les données transmises et le CV ; modifier l'étape ; préciser un motif de refus | Candidature tierce inaccessible ; motif de refus manquant ; « Aucune candidature reçue » ; profil ultérieurement modifié non partagé automatiquement |
| UC09 / administrateur | Ouvrir les comptes inactifs dans l'administration ; examiner la demande ; activer le compte accepté | Accès candidat ou recruteur refusé ; demande refusée : compte maintenu inactif ; distinguer refus et désactivation ultérieure |
| UC10 / administrateur | Ouvrir l'administration du catalogue ; créer ou modifier une entreprise et une offre ; enregistrer | Entreprise inconnue refusée ; entreprise sans offre autorisée ; données invalides refusées |
| UC11 / recruteur et administrateur | Recruteur connecté : vérifier l'e-mail par code puis soumettre l'entreprise ; administrateur : examiner puis valider ; recruteur : voir le statut | Code erroné ou expiré, essais limités, justificatifs incomplets, refus ; le format SIREN ou le domaine d'e-mail seuls ne prouvent pas l'appartenance |

Les erreurs réseau conservent la saisie lorsque possible et proposent de
réessayer. Les écrans distinguent chargement, liste vide et échec. Un refus
d'accès ne révèle pas les données de la ressource tierce.

## 4. Parcours à couvrir dans le prototype

| Parcours | Écrans attendus | Traçabilité |
| --- | --- | --- |
| Espace candidat | Connexion, inscription, confirmation d'attente, refus/erreurs ; catalogue, détail de stage, favori, création de candidature ; tableau de bord, suivi, profil, onboarding et CV | UC01–UC06 ; R1–R6 |
| Espace recruteur | Connexion, inscription, confirmation d'attente, refus/erreurs ; vérification, tableau de bord, liste/édition d'offres, candidatures et détail candidat | UC01, UC02, UC07, UC08, UC11 ; R1, R2, R4–R6 |
| Administration | Catalogue, validation des comptes et des recruteurs | UC09–UC11 ; R1, R6 |

Prototype Figma :
Lien [Figma](https://www.figma.com/design/2zB64zoXsnJQ24R1yysJ72/Intern?node-id=129-2)

Le prototype doit rendre ces parcours cliquables et présenter les états
dégradés, les listes vides ainsi qu'un écran zéro donnant accès à tous les écrans.

## 5. Scénario trois-tiers et données de recette prévues

Le navigateur communique avec l'API Python ; seule la couche métier accède à
PostgreSQL. Pour le scénario du manuel : (1) envoyer les identifiants avec CSRF ;
(2) rechercher le compte en base ; (3) obtenir son empreinte et son état ;
(4) vérifier et créer la session si autorisé ; (5) demander ses candidatures ;
(6) construire la requête à partir de la session ; (7) recevoir les dossiers
autorisés ; (8) renvoyer le JSON à afficher. Le catalogue public ne remplace
pas cette consultation protégée dans la démonstration.

Jeu fictif à préparer à l'étape données : trois candidats actifs dont un sans
candidature, un compte en attente et un administrateur ; trois
recruteurs dont deux rattachés à la même entreprise et un non vérifié ; trois
entreprises dont une sans offre, quatre stages dont un sans candidature et
deux dossiers de candidats différents. Prévoir un CV PDF fictif et des
adresses `example.test`. Les deux recruteurs d'une même entreprise permettent
de vérifier que l'autorisation dépend du propriétaire de l'espace.

## 6. Choix d'adaptation

Le modèle générique est adapté aux parcours candidat, recruteur et
administrateur. Le catalogue est public, tandis que les profils,
CV et candidatures sont protégés par la session et les règles de propriété.

La validation du compte et la vérification de l'entreprise sont deux contrôles
distincts. Le partage d'un CV avec un recruteur intervient uniquement après
une candidature explicite du candidat.
