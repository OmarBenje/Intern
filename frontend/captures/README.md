# Captures des écrans principaux

49 captures réelles dans Chromium, sur React/Vite, Django et PostgreSQL
lancés en local. Aucune réponse API interceptée ou simulée. Données fictives.
Résolution : 1440 × 1000 par défaut, 1440 × 1800 pour la fiche candidat
ouverte dans une fenêtre modale. Capture de toute la hauteur de chaque page.

| Écran | Capture |
| --- | --- |
| Connexion | [01-connexion.png](ecrans/01-connexion.png) |
| Connexion : mot de passe incorrect | [02-connexion-erreur.png](ecrans/02-connexion-erreur.png) |
| Connexion : compte en attente | [03-compte-inactif.png](ecrans/03-compte-inactif.png) |
| Demande de réinitialisation | [04-mot-de-passe-oublie.png](ecrans/04-mot-de-passe-oublie.png) |
| Formulaire de nouveau mot de passe (jeton fictif, sans envoi) | [05-nouveau-mot-de-passe.png](ecrans/05-nouveau-mot-de-passe.png) |
| Inscription candidat : choix du rôle | [6-inscription-candidate-role.png](ecrans/6-inscription-candidate-role.png) |
| Inscription candidat : e-mail | [7-inscription-candidate-email.png](ecrans/7-inscription-candidate-email.png) |
| Inscription candidat : nom | [8-inscription-candidate-nom.png](ecrans/8-inscription-candidate-nom.png) |
| Inscription candidat : mot de passe | [9-inscription-candidate-mot-de-passe.png](ecrans/9-inscription-candidate-mot-de-passe.png) |
| Inscription candidat : confirmation en attente | [10-inscription-candidate-attente.png](ecrans/10-inscription-candidate-attente.png) |
| Inscription recruteur : choix du rôle | [11-inscription-recruiter-role.png](ecrans/11-inscription-recruiter-role.png) |
| Inscription recruteur : e-mail | [12-inscription-recruiter-email.png](ecrans/12-inscription-recruiter-email.png) |
| Inscription recruteur : nom | [13-inscription-recruiter-nom.png](ecrans/13-inscription-recruiter-nom.png) |
| Inscription recruteur : mot de passe | [14-inscription-recruiter-mot-de-passe.png](ecrans/14-inscription-recruiter-mot-de-passe.png) |
| Inscription recruteur : confirmation en attente | [15-inscription-recruiter-attente.png](ecrans/15-inscription-recruiter-attente.png) |
| Tableau de bord candidat | [16-tableau-de-bord.png](ecrans/16-tableau-de-bord.png) |
| Catalogue des stages | [17-catalogue-stages.png](ecrans/17-catalogue-stages.png) |
| Candidatures du candidat | [18-candidatures.png](ecrans/18-candidatures.png) |
| Candidatures à valider | [19-a-valider.png](ecrans/19-a-valider.png) |
| Suivi des candidatures | [20-tracker.png](ecrans/20-tracker.png) |
| Profil et CV candidat | [21-profil.png](ecrans/21-profil.png) |
| Moteur de candidatures | [22-moteur.png](ecrans/22-moteur.png) |
| Configuration : CV | [23-onboarding-cv.png](ecrans/23-onboarding-cv.png) |
| Configuration : adresse | [24-onboarding-adresse.png](ecrans/24-onboarding-adresse.png) |
| Configuration : droit au travail | [25-onboarding-eligibilite.png](ecrans/25-onboarding-eligibilite.png) |
| Page introuvable | [26-page-introuvable.png](ecrans/26-page-introuvable.png) |
| Détail d’un stage | [27-detail-stage.png](ecrans/27-detail-stage.png) |
| Page entreprise | [28-entreprise.png](ecrans/28-entreprise.png) |
| Détail d’une candidature | [29-detail-candidature.png](ecrans/29-detail-candidature.png) |
| Candidat sans candidature | [30-candidatures-vides.png](ecrans/30-candidatures-vides.png) |
| Tableau de bord recruteur | [31-recruteur-tableau-de-bord.png](ecrans/31-recruteur-tableau-de-bord.png) |
| Offres du recruteur | [32-recruteur-offres.png](ecrans/32-recruteur-offres.png) |
| Candidatures reçues | [33-recruteur-candidats.png](ecrans/33-recruteur-candidats.png) |
| Entreprise vérifiée | [34-recruteur-entreprise.png](ecrans/34-recruteur-entreprise.png) |
| Intégrations ATS | [35-recruteur-integrations.png](ecrans/35-recruteur-integrations.png) |
| Nouvelle offre : informations générales | [36-recruteur-nouvelle-offre.png](ecrans/36-recruteur-nouvelle-offre.png) |
| Modifier une offre : informations générales | [37-recruteur-modifier-offre.png](ecrans/37-recruteur-modifier-offre.png) |
| Offre : missions et compétences | [38-recruteur-missions.png](ecrans/38-recruteur-missions.png) |
| Offre : critères de matching | [39-recruteur-matching.png](ecrans/39-recruteur-matching.png) |
| Offre : aperçu avant publication (sans publier) | [40-recruteur-apercu.png](ecrans/40-recruteur-apercu.png) |
| Candidatures reçues pour une offre | [41-recruteur-candidatures-offre.png](ecrans/41-recruteur-candidatures-offre.png) |
| Fiche du candidat reçu | [42-recruteur-fiche-candidat.png](ecrans/42-recruteur-fiche-candidat.png) |
| Vérification professionnelle requise | [43-recruteur-verification.png](ecrans/43-recruteur-verification.png) |
| Connexion Django Admin | [44-administration-connexion.png](ecrans/44-administration-connexion.png) |
| Accueil administration | [45-administration-accueil.png](ecrans/45-administration-accueil.png) |
| Administration : utilisateurs | [46-administration-utilisateurs.png](ecrans/46-administration-utilisateurs.png) |
| Administration : détail et activation d’un utilisateur | [47-administration-utilisateur.png](ecrans/47-administration-utilisateur.png) |
| Administration : offres | [48-administration-offres.png](ecrans/48-administration-offres.png) |
| Administration : détail d’une offre | [49-administration-offre.png](ecrans/49-administration-offre.png) |

Le [manifeste](ecrans/manifest.json) conserve les URL et les dates de capture.
Le formulaire de nouveau mot de passe utilise un jeton fictif : il montre le
rendu, sans prétendre vérifier un lien de réinitialisation valide. Les
assistants de création/modification sont capturés sans publication.

Reproduction depuis Intern : suivre [EXECUTION.md, étape 5](../../EXECUTION.md#étape-5--couche-présentation),
puis lancer `node frontend/scripts/capturer_ecrans.mjs`. Le script crée
deux comptes fictifs en attente ; ne pas l’utiliser sur une base personnelle.

Les quatre fichiers historiques à la racine de ce dossier (connexion.png,
inscription-attente.png, profil-candidat.png, espace-recruteur.png) proviennent
de tests avec API contrôlée. Ils ne font pas partie de la série réelle ci-dessus.
La conformité au prototype Figma reste à comparer écran par écran.
