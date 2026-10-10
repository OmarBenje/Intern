# Étape 1 : Analyse fonctionnelle

Ce dossier contient l'analyse fonctionnelle du projet Intern :

- les acteurs et leurs droits ;
- les règles de gestion R1 à R6 ;
- les cas d'usage UC01 à UC11 ;
- les erreurs et les états vides à prévoir ;
- les parcours à représenter dans le prototype Figma ;
- le scénario d'échange entre le client, l'API et la base de données.

## Livrables

- `cas_d_usage.md` : document source ;
- `cas_d_usage.pdf` : document à remettre ;
- `generer_pdf.py` : génération du PDF ;
- `requirements-docs.txt` : dépendances documentaires.

## Générer le PDF

Depuis la racine du dépôt, avec Python et les dépendances documentaires :

```sh
python -m venv /tmp/intern-docs
/tmp/intern-docs/bin/pip install -r analyse/requirements-docs.txt
/tmp/intern-docs/bin/python analyse/generer_pdf.py
pdfinfo analyse/cas_d_usage.pdf
```

Le contenu doit être modifié dans `cas_d_usage.md`, puis le PDF doit être
régénéré afin de conserver une seule source de vérité.
