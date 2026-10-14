# Étape 15 — Plan de test et vérification du scénario

## Objectif

Reproduire la connexion et la consultation des candidatures personnelles,
avec un plan capable de signaler un échec d'authentification ou de contenu.

## Livrables

| Fichier | Rôle |
| --- | --- |
| [plan.jmx](plan.jmx) | Groupe d'utilisateurs, CSRF, connexion, consultation, cookies et assertions |
| [comptes.csv](comptes.csv) | Vingt candidats fictifs, mots de passe de démonstration et candidature attendue |
| [Peuplement](scripts/preparer_comptes.py) | Création transactionnelle des comptes et de leurs dossiers sur base dédiée |
| [Procédure](PROCEDURE.md) | Préparation, paramètres et reproduction des deux contrôles |
| [Composition de test](compose.test.yaml) | Overlay du déploiement existant pour une base et un proxy isolés |
| [Réussite graphique](resultats/etape15/reussite.png) | Un utilisateur, une itération, trois appels réussis |
| [Échec graphique](resultats/etape15/echec.png) | Mauvais mot de passe, connexion refusée et consultation absente |
| [Résultats CLI réussis](resultats/etape15/reussite.csv) | Échantillons bruts de réussite |
| [Résultats CLI négatifs](resultats/etape15/echec.csv) | HTTP 401 et message de l'assertion déclenchée |
| [Réussite GUI brute](resultats/etape15/gui-reussite.csv) | Trois appels réussis dans l'interface graphique |
| [Échec GUI brut](resultats/etape15/gui-echec.csv) | Refus d'authentification observé dans l'interface graphique |
| [Deux candidats](resultats/etape15/deux-utilisateurs.csv) | Une connexion et deux consultations par candidat |
| [Vérificateur](tests/verifier_etape15.py) | Contrôle des résultats bruts, indépendamment du code de sortie JMeter |

## Prérequis examinés

Les livrables des étapes 1 à 14 et les mesures de référence des étapes 10 et 14
sont présents. Les trois services Docker Engine du déploiement de référence
sont sains et le proxy répond HTTP 200. Aucune VM n'est en marche.
Le démarrage puis l'arrêt des trois VM n'ont pas été rejoués pour ce contrôle :
le proxy VM est enregistré en état `aborted`. Sa disponibilité actuelle reste
à vérifier avant l'étalonnage.

La base de démonstration initiale contient huit comptes et deux candidatures :
elle ne suffit pas pour vingt utilisateurs candidats distincts. Une base dédiée
a donc été initialisée avec les scripts SQL communs, puis complétée par vingt
comptes `mesure01` à `mesure20`, chacun avec une candidature. Un deuxième
peuplement produit exactement le même CSV et ne crée pas de doublons.
Ce jeu est prêt pour reproduction ; son installation et son égalité sur les
deux déploiements restent à confirmer avant les campagnes.

## Vérification observée

Contrôles réels du 14 octobre 2026, avec Apache JMeter 5.6.3 et Java 21,
depuis l'hôte, contre trois conteneurs Docker Engine d'un projet dédié.
Le proxy de test publie le port local 8081 ; la référence conserve 8080.
Les VM restent arrêtées. Les essais utilisent un utilisateur et une itération.

| Cas | CSRF | Connexion | Consultation |
| --- | --- | --- | --- |
| Identifiants corrects | HTTP 200, assertion réussie | HTTP 200, identité et cookie vérifiés | HTTP 200, candidature attendue présente |
| Mot de passe incorrect | HTTP 200, assertion réussie | HTTP 401, assertion en échec | Non exécutée, fil arrêté |

La capture graphique est réalisée sur la fenêtre réelle de JMeter. Le parcours
et ses assertions sont identiques au plan livré ; un écouteur temporaire
sélectionne seulement la vue des résultats pour la capture.

Un contrôle complémentaire avec deux candidats et deux itérations donne huit
appels réussis : une préparation CSRF, une connexion et deux consultations par
candidat. Les assertions de candidature restent satisfaites à chaque lecture.

Après les contrôles, le projet de test est arrêté et son volume conservé.
Les trois services du déploiement de référence restent sains. La composition
livrée, les liens des documents et la compilation des scripts Python ont été
vérifiés.

Les résultats bruts et leurs assertions sont vérifiés par :

```sh
python3 mesure/tests/verifier_etape15.py
```

Les contrôles établissent la vérification technique du scénario. Ils ne
constituent ni une approbation pédagogique ni une mesure de performance.
L'étalonnage, les campagnes et leur comparaison restent à effectuer.
