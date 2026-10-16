# Vérification du modèle physique de référence

Ce rapport conserve les résultats du blueprint SQL isolé. Pour l’implémentation Django livrée ensuite et ses **32 tests**, voir [DATABASE_IMPLEMENTATION.md](DATABASE_IMPLEMENTATION.md).

Date : **28 septembre 2026**. Exécuté avec PostgreSQL **16.14**, Python **3.12**, psycopg **3.3.6**. Le projet utilise Django **6.1.1** ; le vérificateur SQL ne dépend pas de l’ORM pour créer les tables.

## Résultat

**22 vérifications réussies**, dont création du DDL complet : **34 tables métier, associations et exploitation**, en complément de `public.auth_user` déjà présent. Le schéma de test `intern_blueprint`, les utilisateurs de test et leurs données ont été annulés par `ROLLBACK`. L’absence du schéma après annulation a été vérifiée.

Les utilisateurs de test ont des IDs négatifs explicites : la séquence de la table d’authentification existante n’est pas avancée. Aucune migration Django existante n’a été modifiée ni appliquée par ce travail.

| Scénario | Résultat |
|---|---|
| Créer les tables, index, FK composites et vecteur généré | Réussi |
| Créer profil, CV, offre, candidature, révision, accord et run valides | Réussi |
| Référencer le CV d’un autre propriétaire | Refusé par FK |
| Référencer une lettre comme CV courant | Refusé par FK |
| Dupliquer une candidature utilisateur/offre | Refusé par unicité |
| Choisir une source appartenant à une autre offre | Refusé par FK |
| Créer une révision avec un propriétaire différent du dossier | Refusé par FK |
| Ajouter un document d’un autre propriétaire à une révision | Refusé par FK |
| Dupliquer un numéro de révision | Refusé par unicité |
| Attribuer une autorisation au mauvais propriétaire | Refusé par FK |
| Créer deux runs actifs pour un dossier | Refusé par index unique partiel |
| Créer un nouvel essai alors qu’un précédent est incertain | Refusé par index unique partiel |
| Créer un run d’envoi sans autorisation | Refusé par CHECK |
| Rémunération maximum inférieure au minimum | Refusée par CHECK |
| Rémunération négative | Refusée par CHECK |
| Expérience dont la fin précède le début | Refusée par CHECK |
| Préférence de salaire sans devise/période | Refusée par CHECK |
| Supprimer une offre avec une candidature | Refusé par FK |
| Dupliquer une source externe dans un board | Refusé par unicité |
| Dupliquer un favori | Refusé par unicité |
| Rechercher un terme présent dans la description | Réussi via vecteur généré |
| Annuler et vérifier l’absence du schéma de test | Réussi |

## Reproduction

Depuis la racine du projet, avec `DATABASE_URL` fourni par l’environnement et pointant vers une **base de développement PostgreSQL 16 contenant `public.auth_user`** :

```bash
.venv/bin/python docs/database/verify_schema.py
```

Le script crée un schéma neuf et échoue si `intern_blueprint` existe déjà ; il ne supprime jamais un schéma préexistant. Toutes les écritures ont lieu dans une transaction annulée, succès ou erreur. Le compte de connexion doit disposer des permissions nécessaires à cette vérification.

## Limites du résultat

Ce contrôle prouve l’exécutabilité du schéma et les invariants SQL énumérés, **pas l’implémentation du produit**. Il ne teste pas les permissions HTTP, l’immutabilité assurée par les futurs services, la validité temporelle des accords, la concurrence de navigateurs réels, R2, les connecteurs ATS ni les performances à volume de production.

Les doublons de runs sont vérifiés au niveau de la contrainte par insertions successives ; ce n’est pas un test de charge concurrente. Les limites et tests d’intégration encore requis sont explicités dans [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md). Lors de cette vérification initiale, les modèles et migrations applicatives étaient encore inchangés ; l’implémentation ultérieure est documentée dans le rapport lié en tête de page.
