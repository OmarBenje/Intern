# Comparatif Docker : 2 et 4 workers Gunicorn

Campagne : `worker-20261019-103419-13231`. Statut : **complete**.

Ordre : 2 puis 4 workers, puis 4 puis 2. Charges : 150, 180, 200 utilisateurs. Même image, mêmes quotas, même base restaurée pour chaque bloc. Montée 30 s, stabilisation 15 s, plateau 120 s, pause utilisateur 1 s.

| Workers | Série | Utilisateurs | Débit réussi (req/s) | p95 (ms) | Erreurs, essai entier | Plateau valide |
|---:|---:|---:|---:|---:|---:|:---:|
| 2 | 1 | 150 | 146.43 | 60.0 | 0 | oui |
| 2 | 1 | 180 | 162.25 | 237.0 | 0 | oui |
| 2 | 1 | 200 | 163.47 | 373.0 | 0 | oui |
| 4 | 1 | 150 | 147.14 | 25.0 | 0 | oui |
| 4 | 1 | 180 | 176.50 | 32.0 | 0 | oui |
| 4 | 1 | 200 | 195.19 | 60.0 | 0 | oui |
| 4 | 2 | 150 | 147.12 | 24.0 | 0 | oui |
| 4 | 2 | 180 | 176.40 | 30.0 | 0 | oui |
| 4 | 2 | 200 | 195.19 | 55.0 | 0 | oui |
| 2 | 2 | 150 | 146.25 | 74.0 | 0 | oui |
| 2 | 2 | 180 | 161.68 | 251.0 | 0 | oui |
| 2 | 2 | 200 | 162.14 | 385.0 | 0 | oui |

## Interprétation

150 utilisateurs : comparaison non concluante (mesures manquantes, seuil dépassé, erreurs ou répétitions divergentes de plus de 10 %).

180 utilisateurs : variation du débit avec 4 workers : +8.8 % et +9.1 %. Une amélioration dans les deux séries soutient l’hypothèse d’une limite liée aux workers ; croiser avec le p95 et les ressources serveur.

200 utilisateurs : variation du débit avec 4 workers : +19.4 % et +20.4 %. Une amélioration dans les deux séries soutient l’hypothèse d’une limite liée aux workers ; croiser avec le p95 et les ressources serveur.

Les relevés CPU, mémoire, E/S et PostgreSQL figurent dans `serie-*/docker/*/serveurs.json`. Un plateau invalide ne représente pas la charge demandée. Ce diagnostic ne valide pas une capacité maximale VM/Docker.
