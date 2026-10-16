# ADR-001 — Modèle relationnel et historique des candidatures

- Date : 28 septembre 2026
- Statut : accepté pour le schéma, implémenté dans les migrations `0009` à `0014` ; services métier à développer
- Décision détaillée : [DATABASE_SCHEMA.md](../database/DATABASE_SCHEMA.md)
- Preuves métier : [recherche concurrentielle](../research/COMPETITOR_DATABASE_RESEARCH.md)

## Contexte

Intern doit réunir job board, profil, agent de candidature et suivi. PostgreSQL 16 et des modèles Django existent déjà. L’ancienne ébauche préconisait un utilisateur personnalisé avant les premières migrations, mais celles-ci ont depuis été créées. La vision impose un seul CV courant ; les variantes envoyées doivent rester consultables.

La recherche des sources publiques de Simplify, Tsenta, Teal et Huntr confirme les besoins d’historique, de profil réutilisable, de documents par dossier et de validation. Elle ne fournit pas leurs schémas SQL privés. Les API Greenhouse, Lever et Ashby donnent des contrats d’import concrets.

## Décisions proposées

1. Conserver PostgreSQL, le modèle utilisateur actuel et le nom `Offer`. Ne pas casser les migrations pour atteindre une architecture théorique de projet neuf.
2. Séparer offre canonique et annonces sources, avec identifiants contextualisés par board et instance. Les rapprochements incertains ne fusionnent pas automatiquement les offres.
3. Séparer profil mutable, document immuable, dossier de candidature, révision, autorisation et tentative d’agent. Une réussite de préparation n’est pas une soumission.
4. Lier l’accord à l’empreinte des informations, réponses, destination et documents ; arrêter lorsque le formulaire change. Commencer par validation individuelle.
5. Stocker fichiers privés dans R2, uniquement références et métadonnées dans PostgreSQL. Prévoir effacement coordonné et reprises.
6. Combiner contraintes SQL, FK composites et services transactionnels. Mettre en évidence les invariants que le SQL seul ne garantit pas.
7. Utiliser une outbox et des consommateurs idempotents. Tout résultat d’envoi incertain bloque le retry jusqu’à réconciliation.
8. Calculer le matching V1 depuis les données structurées. Pas de moteur vectoriel, d’event sourcing complet ou de microservices requis.

## Alternatives examinées

- **Une grosse table candidature avec réponses et fichier courant** : simple à démarrer, mais perd le contenu effectivement approuvé/envoyé et mélange tentatives et parcours employeur.
- **Tout en JSON** : adapté aux formulaires variables, insuffisant pour les recherches, unicités, propriétaires et références documentaires.
- **Un `User` personnalisé immédiatement** : souhaitable à l’initialisation d’un nouveau projet ; migration disproportionnée ici sans exigence d’authentification nouvelle. À traiter séparément si nécessaire.
- **Copier toutes les fonctions concurrentes dans la V1** : contacts, facturation, email et tableaux personnalisables ne sont pas des exigences arrêtées. Définir leurs futurs liens sans les construire prématurément.
- **Garantie d’envoi exactement une fois via clé locale** : impossible sans coopération du destinataire. Conserver preuve, incertitude et procédure de vérification.

## Conséquences

Le modèle contient davantage de tables que le prototype, mais chacune suit un cycle de vie distinct. Les snapshots dupliquent volontairement les faits utiles ; les mises à jour du profil ne réécrivent pas l’histoire. Le coût principal réside dans les services de validation, de concurrence et de suppression, pas dans le nombre de tables.

Le SQL est une référence exécutable isolée, pas une seconde source de migrations en production. Les migrations Django deviendront la source de vérité de la base appliquée ; ce document et le schéma devront être maintenus avec elles. Le développement pourra rester progressif et pédagogique.
