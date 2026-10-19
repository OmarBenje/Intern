# Comparatif VM : 2 et 4 workers Gunicorn

Campagne : `worker-vm-20261019-143401-202396`. Statut : **complete**.

Ordre : 2 puis 4 workers, puis 4 puis 2. Charges : 80, 100, 130 utilisateurs. Mêmes sources, mêmes ressources VM, même base restaurée pour chaque bloc. Montée 30 s, stabilisation 15 s, plateau 120 s, pause utilisateur 1 s.

| Workers | Série | Utilisateurs | Débit réussi (req/s) | p95 (ms) | Erreurs, essai entier | Plateau valide |
|---:|---:|---:|---:|---:|---:|:---:|
| 2 | 1 | 80 | 77.20 | 78.0 | 0 | oui |
| 2 | 1 | 100 | 86.61 | 301.0 | 0 | oui |
| 2 | 1 | 130 | 86.28 | 708.0 | 0 | oui |
| 4 | 1 | 80 | 77.32 | 59.0 | 0 | oui |
| 4 | 1 | 100 | 94.06 | 155.0 | 0 | oui |
| 4 | 1 | 130 | 96.63 | 521.0 | 0 | oui |
| 4 | 2 | 80 | 77.26 | 61.0 | 0 | oui |
| 4 | 2 | 100 | 93.76 | 157.0 | 0 | oui |
| 4 | 2 | 130 | 99.78 | 443.0 | 0 | oui |
| 2 | 2 | 80 | 76.94 | 96.0 | 0 | oui |
| 2 | 2 | 100 | 83.99 | 333.0 | 0 | oui |
| 2 | 2 | 130 | 84.24 | 721.0 | 0 | oui |

## Interprétation

80 utilisateurs : comparaison non concluante (mesures manquantes, seuil dépassé, erreurs ou répétitions divergentes de plus de 10 %).

100 utilisateurs : comparaison non concluante (mesures manquantes, seuil dépassé, erreurs ou répétitions divergentes de plus de 10 %).

130 utilisateurs : comparaison non concluante (mesures manquantes, seuil dépassé, erreurs ou répétitions divergentes de plus de 10 %).

Les relevés CPU, mémoire, E/S et PostgreSQL figurent dans `serie-*/vm/*/serveurs.json`. Un plateau invalide ne représente pas la charge demandée. Ce diagnostic ne valide pas une capacité maximale VM/Docker.
