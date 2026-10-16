# Couverture V29 — Admission automatique de nouveaux employeurs

## Objectif
Relier les pistes fraîches des flux publics à la file existante AtsProbe, sans
manifeste manuel par employeur. Cette version exploite les flux déjà collectés ;
elle n'ajoute ni moteur de recherche web ni exploration arbitraire de domaines.

## Contrat
- Deux entrées : flux publics et inventaire ats-scrapers déjà importé, dont la
  révision épinglée et la provenance sont vérifiées. Les requêtes ats_registry
  désactivées sont des conteneurs de provenance, pas des tâches à relancer.
  Aucun titre de stage exigé pour ces seules pistes de registre : le probe doit
  justement établir la présence de stages européens avant activation.
- Pistes des fournisseurs publics connus, requêtes activées, observation de moins
  de sept jours et titre de stage. Les mots-clés SQL présélectionnent ; le moteur
  de qualification confirme la nature et la géographie sur le portail officiel.
- Liens directs dans les champs structurés de l'annonce : source_url, apply_url,
  application_url, direct_url, job_url_direct, job_url, url, application_details.url.
  Pas d'URL fabriquée à partir d'un nom ni de lecture de liens privés.
- Canonicalisation par les parseurs ATS existants. Exiger un portail unique et la
  concordance exacte du nom d'employeur et de l'identifiant du portail après
  normalisation typographique. Ceci est un filtre de cohérence, pas une preuve
  universelle de propriété. Les alias et portails ambigus restent à examiner.
- Préserver les sources connues, les refus, les probes désactivées et les backoffs.
- Un compteur partagé transactionnel : au plus 50 nouveaux portails par jour UTC,
  500 pistes par passage. Curseur durable ; passage toutes les cinq minutes tant
  qu'il reste une tranche, sinon reprise le lendemain. Relecture quotidienne des
  preuves fraîches pour retrouver une piste mise à jour.
- Admission candidate désactivée + AtsProbe, jamais import direct. Le probe lit le
  portail ; l'import/publication gardent leurs critères stage confirmé et Europe.
- Provenance conservée : résultat d'origine, fournisseur, lien, titre et date.
- Intégration dans le rôle maintenance, séparée des imports. La commande
  discover_employers partage le quota et respecte la date de prochain passage.

## Validation et limites
Tests d'idempotence, quotas, pause, fraîcheur, ambiguïté, liens non autorisés,
source désactivée et backoff. Pilote sur les pistes réellement présentes puis
vérification des résultats des sondes. Un employeur admis n'est pas encore un
stage ajouté. Les annonces sans lien ATS direct, les alias de marque, certains
identifiants Workday et les fournisseurs non reconnus nécessitent encore une
résolution supplémentaire. Exports dans generated, synthèse seule versionnée.

Le registre épinglé est un inventaire de pistes et peut être plus ancien que sept
jours ; seule sa validation en direct par la sonde établit une opportunité
actuelle. Les offres issues des flux restent soumises à la fraîcheur de sept
jours. Les employeurs déjà présents sont exclus par nom exact, et l'ancienne
activation des flux ne peut pas court-circuiter une sonde existante.
