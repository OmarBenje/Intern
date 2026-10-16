# Moteur d'exigences de langue

1er octobre 2026 — `rules-15`, composant `languages-2`, matcher `rules-2`.

## Objectif

Extraire les langues avec leur modalité et leur preuve, sans exception par annonce
ou entreprise. Une langue citée dans une description n'est pas automatiquement une
langue demandée au candidat. Le pays, la nationalité et la langue de rédaction ne
constituent pas une preuve de maîtrise linguistique.

## Traitement général

`jobboard/services/offer_languages.py` est une projection pure, appelée par le même
enrichissement que les dates/durées. Son lexique couvre 30 codes de langue, avec des
formes anglaises, françaises et allemandes et certaines formes locales.
Sa version et la projection des clauses entrent dans la clé de cache d'enrichissement
afin de reconstruire les faits linguistiques même si une ancienne projection porte
déjà la version globale. Les frontières de blocs restent significatives : modifier
la portée d'une puce invalide le cache, même si le texte aplati est identique.
Les preuves sont comparées au texte décodé des champs ATS conservés, en particulier
les listes dont les retours à la ligne sont échappés dans le JSON brut.

1. Restaurer les retours à la ligne internes des paragraphes ATS tout en conservant
   les frontières de paragraphes et de listes. Rattacher un qualificatif explicite
   comme « fluency in » à sa liste de langues lorsqu'ils sont séparés par l'ATS.
2. Identifier les langues dans l'ordre de la source. Écarter les usages manifestement
   adjectivaux de pays/entreprise et l'emploi verbal de « polish your code ».
3. Séparer les propositions qualifiées, conserver les listes qui partagent leur
   qualificatif : « French required and German preferred » diffère de « Fluent in
   English and French ». Gérer aussi les énumérations avec virgules.
4. Attribuer requis, souhaité, facultatif ou inconnu à chaque groupe. Les marqueurs
   natif, bilingue, courant, fluency/proficiency et leurs formes reconnues décrivent
   une exigence ; desired/preferred/un plus décrivent une préférence ; not required
   décrit une absence explicite d'obligation.
5. Conserver les niveaux tels qu'ils sont écrits, notamment les codes CECRL. Aucune
   conversion de « natif » en C2 et aucun niveau attribué silencieusement à une
   autre langue du groupe. Les variantes regroupées sous un code ISO (par exemple
   Mandarin/Chinese sous `zh`) restent explicites dans la preuve ; leur adéquation
   au profil n'est pas validée automatiquement.
6. Conserver les alternatives « ou/or/oder ». Une structure complexe non résolue
   reste inconnue. Dédupliquer les projections par code ; une préférence répétant
   une obligation n'ajoute pas une seconde langue dans la carte. Une obligation
   contredite par « non requis » est signalée et exclue des obligations exploitables.

## Contrat et consommateurs

Les enveloppes `facts` conservent leur méthode/version, texte de preuve et révision :

- `language_requirements.value` : groupes `{codes, modality, operator, level_text,
  evidence_text}` ; matrice de preuve, sans décision automatique d'éligibilité.
- `required_languages.value` : `{code, evidence_text}` pour les obligations communes.
- `preferred_languages.value` : préférences, toujours non bloquantes.
- `language_alternatives.value` : groupes obligatoires où une des langues suffit.
- `language_conflicts.value` : codes à confirmer, statut conflit.

Le filtre de langue requise accepte une obligation commune ou la présence de la
langue dans un groupe alternatif. Il ne traite pas une préférence comme une
obligation ; `include_unknown` reste respecté. Le matching compare les groupes
alternatifs comme tels et ne demande pas toutes leurs langues. Les préférences
ne deviennent pas des critères d'exclusion. Une liste de langues du profil ne
prouve pas un niveau : le matching demande toujours sa confirmation.

La fiche affiche « Langues requises », « Langues souhaitées », « Langues au choix »
et, si nécessaire, « Langues à confirmer ». Les preuves restent dans Sources et
détails. Tous les choix de langue du lexique sont accessibles dans le filtre.

## Validation et limites

Tests de listes, propositions mixtes, négations, niveau natif, CECRL, variantes de
langue, retours à la ligne, conflits, déduplication, absence d'inférence, provenance
des révisions, invalidation du cache, filtres PostgreSQL, alternatives et matching.
75 tests backend contenu/qualité/matching/API passent dans une base isolée. 16 tests navigateur
fiche/moteur passent ; build et contrôle des tokens réussis.

Le snapshot intermédiaire du catalogue conservé est dans
`docs/research/language-engine-audit-2026-10-01.json`. Il compare les ensembles de
langues à la projection stockée au moment de l'audit et fournit des exemples pour
revue. Il inclut aussi des annonces hors catalogue ; ses compteurs ne mesurent pas
la précision ou le rappel. La collecte continue pendant cette vérification.

Le snapshot couvre 14 233 annonces conservées, y compris des annonces retenues
hors catalogue. Il a notamment révélé des pertes liées aux qualificatifs coupés
par les retours à la ligne et à « couramment » ; ces formes ont ensuite été ajoutées
aux régressions avant la reconstruction finale.

Reconstruction finale `rules-15` / `languages-2` : 15 709 annonces présentes au début
du traitement, jusqu'à l'ID 15 719. La collecte continue indépendamment. La fiche réelle Deliverect
11 232 a été vérifiée via son API avec un shell d'authentification simulé : français
et anglais requis, allemand souhaité, faits reliés à la révision 11 245. Aucun
`pageerror` ni débordement entre 320 et 1440 px. Lint sans erreur, avec avertissements
Fast Refresh et dépendances de hook hors de ces changements.

L'extraction reste déterministe et conservatrice. Elle ne comprend pas toute
formulation ni toute langue. Les clauses inconnues sont conservées ; aucune
précision globale n'est revendiquée sans un corpus indépendant annoté. Les niveaux
dans les groupes complexes et les variantes linguistiques doivent être vérifiés
dans l'extrait source. Aucun appel LLM et aucune inférence depuis le CV.
