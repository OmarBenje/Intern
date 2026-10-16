# Intern — Vision et périmètre du produit

Date : 28 septembre 2026

Ce document rassemble les orientations retenues lors de la discussion initiale. Il décrit la vision du produit, sans constituer encore une spécification technique.

## Vision

**Help people build their dream career.**

Intern est une plateforme de recherche d'opportunités professionnelles qui associe un job board à un agent IA capable de postuler au nom de l'utilisateur.

Le produit s'inspire directement de Simplify et de Tsenta. L'objectif n'est pas de chercher à tout prix une différenciation ou d'inventer une nouvelle catégorie : Intern peut répondre aux mêmes besoins, avec une expérience fiable, agréable et complète.

## Objectif d'apprentissage : Django

Intern est aussi un projet pour apprendre Django en construisant une application concrète. Django est donc retenu pour le backend du projet.

Le développement doit se faire progressivement, avec des explications sur les concepts Django utilisés et les choix d'implémentation, afin de comprendre le code et de gagner en autonomie au fil du projet.

## Expérience centrale

**Découvrir les offres sur Intern → choisir celles qui intéressent l'utilisateur → laisser l'agent postuler → suivre les résultats sur Intern.**

Le job board fait partie du cœur du produit et de sa première version. Intern ne se limite pas à un outil auquel on fournit un lien pour automatiser une candidature.

## Les quatre blocs du produit

### 1. Job board

- Consulter des offres de stages, d'alternances et d'emplois.
- Rechercher des offres et appliquer des filtres.
- Enregistrer des offres dans ses favoris.
- Recevoir des recommandations selon son profil et ses préférences.
- Déclencher une candidature directement depuis une offre avec « Postuler avec Intern ».

### 2. Profil candidat

- Centraliser le CV, les expériences et les compétences.
- Limiter la V1 à un seul CV courant par utilisateur, remplaçable ; conserver les documents propres aux candidatures dans leur historique.
- Renseigner les préférences et contraintes de recherche.
- Réutiliser ces informations pour éviter de les saisir à chaque candidature.
- Fournir à l'agent les informations nécessaires pour préparer des candidatures fidèles au parcours du candidat.

### 3. Agent IA de candidature

- Préparer et adapter les documents à l'offre, notamment le CV et, si nécessaire, la lettre de motivation.
- Remplir les formulaires de candidature avec les informations du profil.
- Soumettre la candidature selon les paramètres de délégation choisis par l'utilisateur.
- Permettre une validation avant l'envoi.
- Donner de la visibilité sur les documents et réponses envoyés, ainsi que sur le résultat de chaque tentative.
- Ne pas inventer de compétences ou d'expériences.

### 4. Suivi centralisé

- Retrouver les candidatures envoyées et les documents associés.
- Suivre les réponses, les entretiens et les prochaines étapes.
- Voir les candidatures qui nécessitent une intervention ou dont l'envoi a échoué.

Les modalités de collecte des réponses et de mise à jour des statuts restent à définir.

## Première version

La première version doit proposer le parcours complet : job board, profil, candidature par agent et suivi.

Pour rendre le développement réaliste, le périmètre initial peut être limité à un ensemble d'offres et de sites de candidature compatibles. Cette limitation ne remet pas en cause la présence du job board dès le départ.

L'import d'une offre par lien peut être une fonction complémentaire, mais il ne remplace pas la découverte des offres sur Intern.

Les fichiers seront hébergés sur Cloudflare. PostgreSQL conservera leurs références et métadonnées. La proposition de schéma est détaillée dans [DATABASE_SCHEMA.md](../database/DATABASE_SCHEMA.md).

## Évolution envisagée

Dans un second temps, l'utilisateur pourrait activer un mode où l'agent sélectionne également les offres selon ses critères, puis postule dans le cadre de la délégation accordée.

L'accompagnement à la préparation des entretiens et à la progression professionnelle est une piste possible pour la vision à long terme ; il n'est pas arrêté comme exigence de la première version.

## Points à préciser

- Public et marchés géographiques à servir au lancement : aucune restriction aux seuls étudiants ou à la France n'a été décidée.
- Sources des offres et méthode de mise à jour du job board.
- Premiers sites de candidature pris en charge par l'agent.
- Paramètres de délégation et situations nécessitant une validation de l'utilisateur.
- Méthode de suivi des réponses et des entretiens.
- Modèle économique et acquisition des premiers utilisateurs.
- Architecture et choix techniques complémentaires à Django, retenu pour le backend.

## Références

- [Simplify](https://simplify.jobs/)
- [Simplify Autopilot](https://help.simplify.jobs/en/help/articles/1784339-getting-started-with-autopilot)
- [Tsenta](https://tsenta.com/ai-agent)

Ces produits servent de références fonctionnelles ; leurs annonces ne constituent pas une validation de la qualité de leur exécution.
