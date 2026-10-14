# Étape 16 — Rapport d'étalonnage

Mesures réelles du 14 octobre 2026 : JMeter 5.6.3 et Java 21, en CLI sur
l'hôte, vers Docker Engine 28.3.3 rootless. Un seul déploiement est actif
pendant chaque contrôle.

## Plafond observé

Ressource Nginx : `/static/admin/css/base.css`, 24 538 octets, HTTP 200 et
contenu CSS vérifiés. Montée de 10 s, stabilisation de 5 s, fenêtre stable
de 60 s, sans temporisation ni accès au métier ou à PostgreSQL.

| Utilisateurs | Débit réussi (req/s) | p95 (ms) | Erreurs | CPU injecteur moyen | CPU hôte moyen |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 587.30 | 3.00 | 0.00 % | 52.3 % | 51.9 % |
| 20 | 3250.15 | 12.00 | 0.00 % | 149.5 % | 96.2 % |

**Plafond observé : 3250.15 req/s à 20 utilisateurs.**
C'est une capacité du chemin injecteur/réseau/proxy, pas une limite intrinsèque
de JMeter. La forte charge de l'hôte justifie l'arrêt de la progression statique.
CPU injecteur : 100 % = un cœur ; CPU hôte : 100 % = les
12 processeurs logiques.

À vingt utilisateurs avec 1 s de réflexion, l'application ne peut dépasser
20 consultations/s : **marge statique de 162.5 fois**.
Réétalonner avant d'augmenter cette charge ou de réduire la temporisation.

## Profil fixé

- **Paliers : 1, 5, 10, 20 candidats distincts.**
- **Montée : 30 s ; stabilisation : 15 s ; fenêtre stable : 120 s.**
- Réflexion : 1000 ms ; une seule connexion par candidat.
- Durée programmée : 170 s, dont 5 s de marge finale pour couvrir toute la fenêtre.

Le fichier [protocole.json](protocole.json) constitue la configuration commune.
Les calculs excluent la montée, la stabilisation et les requêtes traversant
les limites ; chaque utilisateur doit couvrir la fenêtre. La protection de
trente connexions/IP par quinze minutes reste active : prévoir quinze minutes
entre les futurs paliers. Les deux contrôles totalisent vingt connexions,
avec trente secondes de repos entre eux.

## Deux exécutions de contrôle

Chaque contrôle utilise **dix candidats**, le même projet isolé, volume, images,
plan et données fictives. Les empreintes du protocole et des entrées sont
identiques ; les assertions de connexion et de consultation restent actives.

| Exécution | Requêtes stables | Débit réussi (req/s) | Médiane (ms) | p95 (ms) | p99 (ms) | Erreurs |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1176 | 9.800 | 17.00 | 22.00 | 30.25 | 0.00 % |
| 2 | 1175 | 9.792 | 17.00 | 21.00 | 25.00 | 0.00 % |

Écart symétrique : `abs(B - A) / ((A + B) / 2) × 100`.
**Débit : 0.09 % ; latence p95 : 4.65 %.**
Les écarts de débit et de latence p95 restent sous 10 %, sans erreur : le contrôle de répétabilité réussit.
Le p99 varie de 19.00 % : la répétabilité constatée concerne le débit
et le p95 ; les valeurs de queue restent plus variables sur ces fenêtres.

CPU injecteur moyen pendant les contrôles :
4.74 % et 4.82 %
d'un cœur ; charge globale moyenne de l'hôte :
9.93 % et 8.72 %.
L'injecteur ne sature pas pendant les contrôles applicatifs.

## Preuves et limites

[Résultats et empreintes](resultats/etape16/etalonnage.json),
[contrôle 1](resultats/etape16/controle-1/brut.csv),
[contrôle 2](resultats/etape16/controle-2/brut.csv),
[statique à un utilisateur](resultats/etape16/statique-1/brut.csv),
[statique à vingt utilisateurs](resultats/etape16/statique-20/brut.csv).
Configurations, plans générés et relevés CPU/RSS accompagnent les résultats.
Le [précontrôle](resultats/etape16/precontrole/brut.csv) reste séparé des deux
contrôles définitifs au protocole figé.
Reproduction : [procédure](PROCEDURE.md#étalonnage-en-ligne-de-commande).

Les VM démarrent et s'arrêtent proprement ; leur entrée locale 18080 répond
HTTP 200 avec un hôte autorisé, sans modification de sécurité. Les bases
existantes diffèrent (11 comptes VM, 8 Docker) : préparer une base VM dédiée
avec les mêmes scripts et vingt comptes avant la comparaison. Ces contrôles
étalonnent une seule base Docker ; leur résultat dépend du chemin rootless et
de l'état de l'hôte. Le déploiement de référence est remis en marche, données
conservées. Détails : [prérequis vérifiés](resultats/etape16/prerequis.json).

Référence : [bonnes pratiques JMeter](https://jmeter.apache.org/usermanual/best-practices.html).
