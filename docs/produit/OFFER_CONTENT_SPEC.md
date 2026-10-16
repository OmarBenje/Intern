# Fiche de stage : lecture structurée et faits justifiés

Date : 1er octobre 2026. Décision : implémenter la variante « Essentiel d'abord ».
Références : [recherche](../research/2026-10-01-offer-description-enrichment.md) et
[Simplify / Tsenta](../research/2026-10-01-simplify-tsenta-job-descriptions.md).

## Objectif

Permettre de comprendre une offre rapidement : missions, exigences, préférences,
conditions, durée et début. Garder une annonce complète lisible et la formulation
qui justifie chaque information. Une inconnue ne doit jamais devenir une valeur
inventée, une préférence ne doit jamais devenir une obligation.

## Périmètre livré

- Une projection déterministe et persistée dans `OfferEnrichment.content`, avec
  schéma, hash d'entrée et source séparés de la version sémantique du matching.
- Reconstruction de blocs depuis le HTML/listes présents dans les révisions ATS
  conservées : Greenhouse, Ashby, Lever, Workday, SmartRecruiters et descriptions
  HTML génériques. Les listes et la conclusion Lever sont incluses ; les sections
  SmartRecruiters utilisent leurs catégories ATS connues.
  La révision n'est utilisée que si son texte correspond à la description courante.
  Sinon la description courante est structurée sans lui attribuer une fausse source.
- Blocs paragraphes, titres, listes ordonnées/non ordonnées. Aucun HTML distant
  exécuté, aucune URL ou script employeur injecté dans le DOM.
- Rubriques normalisées : poste, entreprise, missions, profil requis, un plus, conditions,
  avantages, recrutement et informations complémentaires. Les titres originaux,
  les phrases et les alternatives sont conservés ; aucun texte traduit ou généré.
- Dates exactes, mois, fenêtres de mois, saisons, début immédiat, échéances ; durées en jours,
  semaines et mois, minimum/maximum et durée préférée séparés. Chaque projection
  contient une preuve. Les conflits sont explicites et ne bloquent pas le matching.
- Une vue « L'essentiel » et une vue « Annonce complète », accessibles au clavier,
  avec faits prioritaires en tête et preuves regroupées dans « Sources et détails ».
  La carte n'affiche plus de contrôle « Voir l'extrait ». Le panneau de
  candidature reste visible sur ordinateur et précède le texte sur mobile.
- Extraction de phrases d'exigence (compétences, formation, langues, convention,
  disponibilité et autorisation de travail) ; conservation du texte, modalité et
  alternatives sans prétendre vérifier automatiquement toute l'éligibilité.
- Aucun appel LLM nécessaire pour cette version. La structure et les faits sont
  produits hors affichage ; une génération sémantique ultérieure devra être
  évaluée sur un corpus annoté avant activation. « L'essentiel » réorganise les
  passages sources et ne prétend pas produire un résumé exhaustif par IA.

## Contrat

`GET /api/v1/offers/<id>/` ajoute `content` :

- `schema_version`, `input_hash`, `source_revision_id`.
- `blocks`: objets `{id, kind, text}` ou `{id, kind, items}` pour les listes.
- `sections`: `{kind, original_heading, block_ids}`.
- `requirements`: `{text, category, modality, alternative, block_id}`.

Les `facts` existants gardent leurs enveloppes de preuve. `start_date` reste une
date ISO exacte ; `start_period` représente un mois/fenêtre de mois/saison/immediate/ambigu et ne
fournit pas de date fictive. `duration.value.maximum` peut être nul pour une borne
minimale seule. `preferred_duration` est distinct et non bloquant. Une échéance
horaire sans fuseau reste une formulation à confirmer. Les métadonnées de source
comme `publishedAt` ou `application_deadline` sont distinguées du texte du stage.

Les filtres de date exacte traitent les périodes comme inconnues, conformément à
`include_unknown`. Les bornes de durée ouvertes sont comparées comme telles et
les jours/semaines se convertissent exactement. Aucun mois n'est assimilé à 30 jours.

## Sources et cache

Préférer les révisions des sources actives, de la plus récente à la plus ancienne.
Ne jamais remplacer le texte courant par un ancien payload divergent. Les titres
de section seuls ne changent pas la classification de l'offre. Les faits de source
structurée sont acceptés uniquement depuis la révision sélectionnée et ne prennent
pas le dessus silencieusement sur une contradiction du texte.

L'import et `re_enrich_catalogue` construisent la projection. Une variation de
HTML ou de révision renouvelle la présentation même si le hash sémantique est
identique. Une lecture API n'écrit pas en base ; une offre sans projection reçoit
un repli déterministe sur sa description.

## Critères d'acceptation

1. Une liste HTML sans puces textuelles apparaît comme une liste ; un titre en
   gras isolé devient un intertitre. Les éléments et leur ordre restent accessibles.
2. « À partir de mai 2027 » affiche le mois ; « starting June 2, 2027 » fournit une
   date exacte ; « Summer 2027 » reste une saison ; `02/03/2027` sans convention
   explicite reste ambigu. Une date impossible est ignorée.
3. « Minimum 3 months, ideally 6 » affiche deux contraintes distinctes et n'impose
   pas 6 mois au matching. « 6 months experience » n'est pas une durée de stage.
4. Une préférence de langue ne masque pas une langue obligatoire dans une autre
   proposition de la même phrase ; « Python or Java » reste une alternative.
5. Deux débuts/durées incompatibles affichent un conflit avec leurs preuves ; aucune
   incompatibilité candidate ne résulte d'une valeur conflictuelle ou non sourcée.
6. Une deadline ne devient pas un début de stage. Publication, échéance et
   vérification portent des libellés distincts.
7. Un script, style, attribut événement ou URL dangereuse dans la source n'est
   jamais exécuté. Les rubriques inconnues restent visibles dans l'annonce complète.
8. Tests backend de parsing/provenance/idempotence/filtres/matching ; tests navigateur
   des vues, clavier, états vides, liens externes et absence de débordement à
   320, 390, 768 et 1440 px. Build, lint et migration vérifiés.

## Limites attendues

Pas de garantie d'extraction exhaustive sur toute langue ou toute formulation.
Conserver les formulations non reconnues dans le contenu ; absence de rubrique
ne signifie pas absence d'exigence. Les documents/questions requis du formulaire
ATS ne sont pas déduits automatiquement de cette seule description. Une extension
LLM et un score de compatibilité détaillé restent soumis à validation spécifique.

## Livraison et vérification locale

- Migration `0024_offer_content` appliquée ; projection `offer-content-1` et règles
  `rules-10` reconstruites pour les 11 247 annonces locales. Ce nombre inclut les
  annonces retenues hors catalogue : il ne mesure pas la qualité de l'extraction.
- 405 tests backend réussis (`manage.py test jobboard --noinput`) ; 15 tests navigateur
  fiche/moteur réussis ; build et contrôle des tokens réussis. Lint sans erreur,
  avec trois avertissements Fast Refresh dans `EngineControls.tsx`.
- Lecture du vrai endpoint de l'annonce Sanofi 2512, shell d'authentification simulé
  pour la revue navigateur : durée 6 mois, fenêtre janvier–mars 2027, listes et
  profil reconstruits depuis sa révision Workday. Aucun débordement à 320, 390,
  768 ou 1440 px ; contrôles clavier des onglets et accès aux sources ; capture avec tokens
  sombres et préférence de mouvement réduit.
- La couverture de ces tests valide les cas spécifiés ; la précision globale sur
  le catalogue n'a pas été mesurée sur un corpus annoté. Livraison locale, sans
  déploiement distant.

### Correctif de début élidé (1er octobre)

La règle initiale reconnaissait « à partir de », mais ignorait « à partir d'octobre »
et « à partir d’octobre ». `rules-11` accepte les deux apostrophes sans inventer de
jour : l'offre Natixis 9297 porte désormais `start_period = 2026-10`, précision
mois et relation `from`, reliée à la révision 9310. Les 49 descriptions locales
contenant cette forme ont été recalculées ; les autres projections seront renouvelées
par le cycle normal d'enrichissement. Régression backend couvrant les deux apostrophes
et un espace après l'apostrophe ; 60 tests contenu/qualité/matching/API réussis dans
une base de test isolée.
Affichage réel de 9297 vérifié via son endpoint local : « À partir d’octobre 2026 ».
Build réussi et 15 tests navigateur vérifiés (un timeout à l'installation des mocks
avant chargement de la page a nécessité une relance ciblée, réussie en 3,1 secondes).

### Moteur de langues

Le traitement des langues a ensuite été remplacé par un module commun de
propositions, modalités, alternatives et preuves. Il ne contient aucune exception
pour une annonce ou une entreprise. Voir [la spécification du moteur de langues](../moteur/LANGUAGE_ENGINE_SPEC.md).
