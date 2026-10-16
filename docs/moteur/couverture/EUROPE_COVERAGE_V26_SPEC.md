# Couverture V26 — Stages signalés : Sentry et Microsoft

## Problème et objectif
Un stage Sentry à Vienne et un stage Microsoft signalé par l'utilisateur manquent au catalogue. Vérifier leurs sources officielles, corriger les causes constatées, importer les stages européens confirmés et conserver une collecte régulière. Ne pas assimiler les postes New Grad à des stages ni élargir automatiquement la portée des postes entièrement à distance.

## Constats et changements
- Sentry : portail Ashby absent du registre. Admission par manifeste revu, candidat 1780, sonde 268.
- Ashby : l'annonce à Vienne indique `workplaceType=Hybrid` et `isRemote=true`. Le booléen seul faisait classer l'annonce en télétravail intégral et rendait son périmètre européen incertain. Priorité aux valeurs documentées `Hybrid`, `OnSite`, `Remote`; repli sur `isRemote` quand l'enum est absent ou inconnu.
- Microsoft : portail Eightfold 458 déjà enregistré mais sans import réussi, collecte suspendue après HTTP 429. Ajouter un intervalle minimal de deux secondes entre départs de requêtes dans une collecte. Garder le budget de cinq minutes, les limites de pagination et les délais de reprise existants. Aucun nouvel essai immédiat après 429.
- Vérifier le stage Microsoft repéré via des index secondaires auprès du portail officiel avant publication. Les index ne prouvent pas sa disponibilité actuelle.

## Acceptation
- Sentry Summer 2027 visible en Autriche et hybride ; portail actif et planifié.
- Non-régression : remote reste géographiquement incertain, New Grad non assimilé, annonce non listée exclue.
- Les appels Eightfold sont espacés et une limitation ne provoque pas de boucle de réessais.
- Documenter séparément les fiches réellement visibles et les sources encore bloquées ; aucune promesse d'exhaustivité.

## Sources
- https://developers.ashbyhq.com/docs/public-job-posting-api
- https://jobs.ashbyhq.com/sentry/fa522ac5-fc9f-4ce1-a191-842496a235a2
- https://builtin.com/job/software-engineer-internship-opportunities/11393031 (découverte)
- https://rezeume.com/jobs/microsoft/1970393557007677 (découverte)
