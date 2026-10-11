# Vérification de la couche présentation

## Organisation et cohérence

Le frontend est une application React/TypeScript servie par Vite. `src/App.tsx`
déclare les routes et les gardes ; `src/auth/` gère la session ; `src/lib/api.ts`
centralise les appels HTTP, les cookies et le CSRF ; `src/pages/` contient les
écrans candidat et recruteur ; `src/components/` fournit les éléments partagés.
Les tests navigateur sont regroupés sous `tests/` et les captures de livraison
sous [captures/](captures/README.md). Les pages utilisent l'API REST, avec
états de chargement, d'erreur et d'absence de résultat sur les parcours testés.

La comparaison des contrats frontend/API a révélé que l'inscription crée un
compte **en attente d'activation**. L'écran confirme désormais cet état sans
ouvrir de session. Une tentative de connexion avant activation donne un message
explicite. Les téléchargements de CV et les images fournies par l'API utilisent
le préfixe `VITE_API_ROOT`, partagé avec le proxy de développement. Les filtres
du catalogue gardent leurs saisies lorsque l'URL est mise à jour rapidement et
se réinitialisent avec les critères appliqués. La route inconnue affiche une
page 404 explicite.

L'application n'introduit pas de second client HTTP ni de copie des écrans :
les nouveaux parcours reprennent les modules et les composants existants.

## Lancer et contrôler

Depuis la racine d'Intern, démarrer PostgreSQL et l'API selon
[le guide métier](../metier/README.md), puis dans un autre terminal :

```sh
cd frontend
npm ci
npm run dev
```

Ouvrir `http://127.0.0.1:5173/login`. Les détails de configuration du proxy,
du préfixe API et de l'origine CSRF sont dans [le guide frontend](README.md).

```sh
cd frontend
npm run build
npm run lint
npm run test:e2e
```

La compilation, l'analyse statique et les tests Playwright vérifient le rendu
et les appels REST avec réponses contrôlées. Les captures sont liées dans
[leur index](captures/README.md). Le test navigateur ne remplace pas une recette
interactive contre les trois services réels. Le prototype externe reste à
comparer visuellement dans son interface, notamment pour l'administration.

## Résultats et limites

Le build de production passe. Vite signale un fichier JavaScript d'environ
506 Ko après minification : une séparation des routes réduirait le chargement
initial, mais n'empêche pas le fonctionnement. Le lint passe avec trois
avertissements `react(only-export-components)` sur les exports mixtes de
`EngineControls.tsx`. Un build avec `VITE_API_ROOT=/intern/api` a également
réussi et incorporé ce préfixe ; le build par défaut a ensuite été rétabli.
La suite Playwright complète a donné **104 tests réussis
et 3 scénarios optionnels ignorés**. Après le dernier correctif de navigation,
les **8 tests du catalogue** et le parcours d'inscription utilisé pour la
capture ont été rejoués avec succès ; le build et le lint ont aussi été relancés.
Les trois scénarios ignorés concernent le fournisseur externe de logos.

Les captures utilisent uniquement des identités fictives. L'accès au prototype
et un déploiement réel avec API et base de données demandent une vérification
séparée avant présentation au jury.
