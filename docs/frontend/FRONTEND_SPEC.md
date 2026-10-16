# Intern — Couche métier frontend : plan et première livraison

Date : 30 septembre 2026. Contrat : [API v1](../backend/API.md), [vision](../produit/VISION.md),
[état réel du backend](../backend/BACKEND_IMPLEMENTATION.md).

## État au 30 septembre 2026

La livraison comprend la connexion par e-mail, l’inscription, le reset, la garde de
session et la déconnexion, ainsi que l’onboarding connecté obligatoire en trois étapes :
CV privé, adresse et autorisations de travail. Le profil regroupe désormais les informations personnelles, compétences, expériences,
formations, projets, liens professionnels, préférences de recherche, adresse et
autorisations de travail, ainsi que le téléchargement et le remplacement du CV.
Les formulaires utilisent les API existantes ; voir [détails du profil](../design/profile.md). Les sélecteurs de pays sont personnalisés et utilisables au clavier.
Le thème orange/gris, les icônes Hugeicons et les animations courtes partagent les
tokens du frontend. La réduction des mouvements est respectée. Sur mobile, le panneau
décoratif de connexion est masqué. Pas de boutons OAuth sans intégration.

Les services génériques et le contrôleur de candidature décrits ci-dessous restent
**planifiés, non implémentés**. Les espaces métier existants restent provisoires.
Les vérifications navigateur sont dans `frontend/tests/` : API contrôlée, aucune
soumission ou opération réelle sur un compte. Les tests Django vérifient séparément
les endpoints d’authentification, de documents et d’onboarding.

## Périmètre de la couche métier planifiée

Implémenter une couche TypeScript indépendante de React, réutilisable par les futurs
écrans. Aucun nouvel écran, formulaire, composant visuel ou changement de navigation.
Le backend conserve les règles métier, les contrôles de propriétaire et les transactions.
Le frontend gère les commandes, les états de session, les données typées et le consentement
portant sur une révision précise. Il ne génère ni expérience professionnelle ni texte IA.

## Recommandations vérifiées

- [React — synchronisation](https://react.dev/reference/react/useEffect) : les réponses
  anciennes ne doivent pas remplacer des données plus récentes. Transport annulable et
  invalidation des requêtes à chaque changement de session ; abonnements utilisables
  plus tard par React. Les mutations partent d'une commande explicite, jamais d'un effet.
- [Django — CSRF AJAX](https://docs.djangoproject.com/en/6.0/howto/csrf/) : sessions par
  cookies, X-CSRFToken sur toutes les mutations, rotation après authentification,
  requêtes de même origine. Aucun jeton de session dans le stockage navigateur.
- [W3C — notifications de formulaires](https://www.w3.org/WAI/tutorials/forms/notifications/) :
  conserver les détails des erreurs serveur et distinguer attente, succès, échec et
  résultat inconnu pour les futurs formulaires. L'accessibilité visuelle sera vérifiée
  lorsque les écrans seront construits.
- [React Router — navigation](https://reactrouter.com/start/declarative/navigating) :
  les futurs écrans pourront utiliser Link/NavLink ; aucune modification du routeur ici.
- [Recherche concurrentielle](../research/COMPETITOR_DATABASE_RESEARCH.md) et vision actuelle :
  distinguer offre, profil, dossier versionné, autorisation d'envoi et suivi. Les types
  couvrent tous les contrats et les données inconnues, sans restriction géographique.

## Services et contrats

1. **Session** : restaurer, inscrire, connecter et déconnecter ; observer les états.
   Une réponse 401 privée invalide la session ; une panne n'est pas assimilée à une
   identité anonyme. Changement/reset de mot de passe, export ZIP et suppression du
   compte avec mot de passe sont exposés. Pas de credentials conservés côté navigateur.
2. **Profil** : lire/corriger les champs explicites ; CRUD typé des expériences,
   formations, projets et autorisations de travail ; listes paginées. Les identités
   ne sont pas dérivées du nom complet. Absence de profil/préférences normalisée à null.
3. **Préférences** : mise à jour partielle conservant les champs omis, tableaux vides et
   valeurs nulles ; salaire avec devise/période/brut-net. Catalogue rôles/lieux/compétences
   recherchable et paginé. Aucune comparaison de salaire inventée côté client.
4. **Documents** : PDF (10 Mio max), type CV/lettre, multipart avec boundary navigateur,
   liste, téléchargement privé, sélection du CV courant et suppression. Prévalidation
   ergonomique du fichier ; le serveur vérifie le contenu et protège les documents liés.
5. **Offres** : recherche/filtres/pagination, détail, favoris idempotents et recommandations
   avec raisons, champs inconnus et comparabilité du salaire. Description conservée en
   texte ; helper de lien externe HTTP(S) pour les futurs composants.
6. **Dossiers** : création/reprise idempotente, préparation, correction complète des
   réponses/pièces, lecture des snapshots et historiques paginés. Le client conserve
   les types des choix ATS (nombre ou chaîne) et les choix multiples.
7. **Relecture et envoi** : contrôleur observable lié au compte et au dossier ; révision
   affichable immuable et brouillon séparé. Une correction invalide la confirmation.
   L'approbation exige une confirmation explicite, aucune modification non sauvegardée,
   aucun champ manquant ni formulaire non pris en charge ni exécution bloquante.
   Le serveur vérifie encore source, accord, documents et révision.
8. **Idempotence** : avant l'appel, enregistrer dans sessionStorage uniquement l'ID de
   révision, son hash et un UUID, sous une clé par compte/dossier. Aucun contenu personnel.
   Un double clic est bloqué. Un résultat réseau ambigu conserve cette commande et
   bloque toute nouvelle autorisation/correction ; `retryApproval()` rejoue explicitement
   la même commande, y compris après rechargement. Aucun retry automatique. Une réponse
   définitive résout cette tentative ; les 409 imposent une nouvelle lecture avant accord.
   Si le stockage est indisponible, l'approbation est bloquée avant tout appel réseau.
9. **Suivi** : statut de recrutement distinct de l'exécution. Révocation explicite avant
   effet externe ; résolution humaine d'incertitude avec preuve ; tâches et entretiens
   CRUD ; événements, exécutions et révisions paginés. Aucun email/calendrier envoyé
   par ces services et aucune soumission déclenchée dans les tests.

## Architecture et garanties

- `src/lib/api.ts` : transport injecté/testable, erreurs structurées, CSRF partagé,
  annulation, délais bornés, téléchargements, invalidation de session. Compatibilité
  avec les exports initiaux `apiRequest`, `refreshCsrfToken`, `ApiError`.
- `src/lib/intern/types.ts` : lectures/commandes distinctes, pagination et enums du backend.
- `src/lib/intern/client.ts` : façade des services et magasin observable de session.
- `src/lib/intern/workflow.ts` : contrôleur de préparation/relecture/approbation.
- `src/lib/intern/helpers.ts` : paramètres, liens, fichier PDF et stockage d'approbation.

Aucun cache persistant des profils, réponses, CV ou secrets. Réinitialisation du transport
et invalidation des contrôleurs à la sortie/changement du compte. Le backend reste seul
habilité à autoriser une mutation. Une commande frontend exposée n'est jamais exécutée
sans un appel explicite du futur écran.

## Vérification prévue pour la couche métier planifiée

Tests Node exécutant les vrais services et contrôleurs avec un transport HTTP contrôlé :
CSRF, rotation, expiration, erreurs JSON/HTML/réseau, aucune relance implicite, annulation,
profil/préférences/documents/catalogue, révision exacte, correction, double clic,
idempotence après coupure/rechargement, conflits, formulaire non compatible, envoi incertain,
isolation des comptes, tâches/entretiens, export et suppression. Compilation TypeScript,
lint et build Vite. Pas de tests visuels puisqu'aucun écran n'est demandé.

Les doubles HTTP vérifient le contrat client mais ne prouvent pas le fonctionnement
distant. Le stockage privé du CV peut utiliser R2, configuré côté serveur dans le `.env`
local ignoré par Git. L’envoi vers les ATS, l’extraction CV et la rédaction IA ne sont
pas inclus dans le parcours livré. La livraison des e-mails dépend du backend configuré.
