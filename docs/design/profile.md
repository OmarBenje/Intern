# Profil candidat — 30 septembre 2026

La page `/profil` regroupe désormais les informations confirmées du candidat et son CV courant. Elle remplace l’ancien écran limité au téléchargement/remplacement du CV, tout en réutilisant ce parcours pour l’onboarding.

## Recommandations appliquées

- `docs/produit/VISION.md` : centraliser CV, expériences, compétences et préférences ; conserver un seul CV courant.
- `docs/research/COMPETITOR_DATABASE_RESEARCH.md`, S1/S2 : séparer document et faits confirmés, sans écraser les corrections manuelles lors d’un remplacement du CV.
- `docs/frontend/FRONTEND_SPEC.md`, profil/préférences/documents : utiliser les API existantes, distinguer les valeurs inconnues des réponses négatives, préserver les détails des erreurs, rechercher et paginer les catalogues.
- Skill `better-ui` : réutiliser les couleurs, espacements, rayons et contrôles de l’interface ; navigation au clavier, états d’attente et retours explicites.

## Fonctionnement

Sections : identité, présentation, coordonnées, disponibilité, CV avec nom et taille du fichier, compétences, expériences, formations, projets, liens professionnels, préférences de recherche, adresse et autorisations de travail. Les nationalités et déclarations complètes restent modifiables via le formulaire d’éligibilité existant.

Chaque section conserve son brouillon et n’envoie que ses champs. Enregistrer, annuler et supprimer sont des actions explicites. Une erreur laisse les valeurs saisies en place. Les suppressions demandent une confirmation locale. Les changements du profil ne démontent pas les autres formulaires ouverts. Les liens vers une autre page et le rechargement préviennent en cas de brouillon modifié ; le bouton Précédent du navigateur n’est pas intercepté.

Le salaire est saisi avec sa devise, sa période et sa base brut/net. Un montant vide désactive le seuil. Sans contrat et mode de travail acceptés, la page explique pourquoi il faut compléter les préférences pour recevoir des recommandations.

Les autorisations conservent trois états (oui, non, inconnu). Prénom et nom ne sont jamais déduits du nom affiché. Aucun contenu n’est inventé depuis le CV et aucun fournisseur d’extraction n’est ajouté. Les indicateurs de complétude portent uniquement sur quatre essentiels explicitement nommés, pas sur une note de candidature.

## Vérification

`frontend/tests/profile.spec.ts` couvre enregistrement et relecture, isolation des brouillons, CRUD, validation des dates et du salaire, erreurs et reprise, valeurs nulles, annulation, navigation avec brouillon, CSRF et largeurs 320–1440 px. Les API de ces tests navigateur sont contrôlées ; elles ne modifient pas le compte réel.

Les suites Django `test_profiles_api` et `test_documents_api` vérifient séparément les services et endpoints réels sur la base de tests. Le rendu et les lectures authentifiées ont également été vérifiés dans Chrome sur le serveur local. Aucun enregistrement de données fictives sur le compte utilisateur.
