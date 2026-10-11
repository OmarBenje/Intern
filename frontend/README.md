# Intern — frontend

React, TypeScript, Vite et React Router. La connexion, l’inscription, la réinitialisation du mot de passe et l’onboarding connecté sont implémentés. Le parcours obligatoire comprend le CV privé, l’adresse et les autorisations de travail ; `/profil` permet ensuite de télécharger ou remplacer le CV.

## Démarrer

Node.js 20.19+ ou 22.12+ :

```bash
cd frontend
npm ci
npm run dev
```

Ouvrir <http://127.0.0.1:5173/login>. Vite transmet `/api` et `/health` au backend sur `127.0.0.1:8000`. Pour les mutations protégées par CSRF, lancer Django avec l'origine du serveur Vite autorisée :

```bash
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173 uv run --project ../metier ../metier/app/manage.py runserver 127.0.0.1:8000
```

Utiliser la même adresse (`127.0.0.1`) dans le navigateur. Le backend, PostgreSQL et le worker se démarrent suivant le [README principal](../README.md). En production, servir le build et l'API sous une même origine ; le proxy Vite ne fonctionne qu'en développement.

## Repères

- `src/App.tsx` : routes publiques de connexion/reset, garde de session et emplacements des quatre espaces produit.
- `src/auth/` : session en mémoire, vérification de l’identité, connexion/déconnexion et erreurs.
- `src/pages/Login.tsx` et `src/pages/ResetPassword.tsx` : formulaires reliés au backend.
- `src/components/auth/` : `AuthLayout`, `AuthVisual`, champs, contrôle du mot de passe, bouton et notifications. Passer `imageSrc` à `AuthLayout` pour remplacer l’emplacement visuel ; l’image est décorative et recadrée avec `object-fit: cover`.
- `src/lib/api.ts` : `apiRequest<T>()` pour les appels JSON ou `FormData`. Il conserve les cookies de session et le jeton CSRF, y compris après rotation lors d'une connexion. Une mutation échouée n'est jamais relancée automatiquement.
- `src/tokens.css` : espacements, arrondis, typographie, tailles, focus et mouvement. Voir [DESIGN.md](DESIGN.md) pour les règles et sources.
- `src/theme.css` : palettes orange et grise (12 nuances, variantes alpha et P3/OKLCH), puis tokens sémantiques. Le thème clair est activé sur `<html class="light">` (la palette sombre reste disponible) dans `index.html`.
- `src/index.css` et `src/App.css` : styles globaux et composants utilisant les tokens du thème.

Pour les composants, utiliser `--background`, `--surface`, `--text`, `--muted`, `--border`, `--accent`, `--accent-hover` et `--focus-ring`. Le texte sur un fond `--accent` utilise `--on-accent` (sombre) ; les liens et libellés accentués utilisent `--accent-text`. Le token primitif `--orange-contrast` fourni reste inchangé, mais le blanc est insuffisamment contrasté pour du petit texte sur cet orange.

Exemple :

```ts
const offers = await apiRequest<{ results: unknown[] }>('/offers/')
```

Vérifications : `npm run check:tokens`, `npm run build`, `npm run lint` et `npm run test:e2e`.

## Connexion et vérifications navigateur

Le formulaire utilise une **adresse e-mail** ; l’API conserve aussi la connexion par
nom d’utilisateur pour les anciens comptes. Aucun compte de démonstration ni connexion
Google/GitHub n’est ajouté. Créer un compte ou utiliser un compte candidat existant
pour un essai réel. Les mots de passe ne sont pas stockés dans localStorage/sessionStorage.
Après succès, retour à l’espace demandé ou `/dashboard`, avec reprise obligatoire de
l’onboarding s’il reste incomplet.

Le reset appelle les endpoints Django existants. Pour ouvrir le lien de l’email en
développement, démarrer Django avec `PUBLIC_BASE_URL=http://127.0.0.1:5173` en plus de
`CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173`. La livraison d’email dépend du backend configuré.

```bash
npm run test:e2e
```

Les tests Playwright utilisent Google Chrome installé (`channel: chrome`), un serveur
Vite isolé sur le port 5174 et des réponses API contrôlées. Ils ne nécessitent pas Django
et n’envoient aucun email. Un seul navigateur est lancé à la fois pour limiter l’espace
temporaire. Pour CI, installer Chrome avec `npx playwright install chrome` ou adapter
le canal dans `playwright.config.ts`.

## Labels et aides de saisie

Les champs d’authentification gardent leurs labels visibles au-dessus de la saisie.
Les placeholders redondants sont supprimés ; une consigne utile utilise `hint` dans
`AuthField`, affichée sous le champ et reliée avec `aria-describedby`, y compris
après saisie. Le reset précise ainsi d’utiliser l’adresse associée au compte.

Ce choix suit les [recommandations de formulaires du design system W3C](https://design-system.w3.org/styles/forms.html)
et le [guide WAI sur les labels](https://www.w3.org/WAI/tutorials/forms/labels/).
Il s’agit d’un choix UX pour ces formulaires, pas d’une interdiction générale des
placeholders imposée par WCAG.

## CV et stockage privé

Le navigateur envoie le PDF à Django (`POST /documents/`), puis associe le document au profil (`PUT /profile/resume/`). Les secrets R2 restent côté serveur. Le bucket reste privé ; aucun CORS R2 ni domaine public n’est nécessaire. Si l’association échoue après l’envoi, le bouton de reprise conserve l’ID du document sans réenvoyer son contenu. Après rechargement, le CV courant est relu depuis le profil.

Pour activer la configuration R2 locale : `uv run --project ../metier --env-file ../metier/.env ../metier/app/manage.py runserver 127.0.0.1:8000` depuis la racine. Utiliser aussi `--env-file .env` pour le worker. Le PDF est limité à 10 Mio et contrôlé côté serveur. L’extraction IA n’est pas incluse dans ce parcours.

## Onboarding obligatoire

Le parcours connecté comporte trois étapes : `/onboarding/resume`, `/onboarding/address`, puis `/onboarding/work-eligibility`. Le serveur retourne `onboarding_step` dans la session ; les pages privées redirigent vers la première étape non terminée. Les étapes précédentes restent accessibles pour correction. Le CV est obligatoire. L’adresse est enregistrée au clic sur Continuer et la dernière étape valide les réponses avant de marquer l’onboarding terminé. Les nouveaux champs sont ajoutés par la migration `0016_candidate_onboarding`, sans considérer les comptes existants comme déjà terminés. La nationalité et les subdivisions d’adresse sont facultatives ; au moins un pays de travail et des réponses explicites sont nécessaires.

## Tableau de bord

`/dashboard` reprend la palette crème/encre/orange, DM Sans, Instrument Serif et les
arrondis des pages de connexion. Ces valeurs sont partagées via `--brand-*` et
`--font-brand-*` ; la densité du tableau de bord reste adaptée à un outil de travail.
La référence visuelle guide la structure (navigation, quatre offres, tableau), sans
pourcentages de compatibilité ni données de démonstration dans l’application.

`GET /api/v1/dashboard/` fournit les quatre dernières offres ouvertes, les dossiers
paginés du compte, les documents de leur dernière révision et les compteurs. `q`,
`filter`, `page` et `page_size` contrôlent la recherche et la sélection. La lecture
n’autorise ni ne déclenche aucun envoi. Les cartes ouvrent `/offers/:id`, où les liens
de candidature existants sont disponibles ; `/applications/:id` affiche le suivi.
Le bouton « Tout vérifier » ouvre `/a-valider`. La relecture et l’envoi automatisé
ne sont pas implémentés par cette interface.

Les logos d’entreprise sont représentés par des initiales tant que l’API ne fournit
pas de fichiers publics. Le nom affiché en bas provient du profil du compte. Les
captures de `tests/dashboard.spec.ts` utilisent uniquement des fixtures isolées.
