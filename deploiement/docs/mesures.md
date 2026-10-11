# Mesures de référence — trois VM

Relevés réels du **12/10/2026**, avec trois séries complètes et dix appels de
consultation par série. Le [protocole reproductible](../VERIFICATION.md) définit
les seuils de démarrage, le repos de trente secondes et les méthodes de lecture.
Les [valeurs brutes et la configuration](mesures-etape10.json) sont conservées.

## Configuration mesurée

| Paramètre | Valeur |
| --- | --- |
| Hôte | Fedora Linux 42 (KDE Plasma Desktop Edition), noyau 6.19.14-108.fc42.x86_64 |
| Processeur | 12th Gen Intel(R) Core(TM) i5-1235U ; 12 processeurs logiques |
| RAM totale de l'hôte | 15.297 Gio |
| VirtualBox | 7.2.8_RPMFUSIONr173730 |
| Invités | Ubuntu Server 24.04.5 LTS, sans interface graphique |
| vm-proxy | 1 vCPU, 1 Gio, paravirtualisation minimal |
| vm-metier | 2 vCPU, 2 Gio, paravirtualisation default/KVM |
| vm-donnees | 2 vCPU, 2 Gio, paravirtualisation default/KVM |
| Disques | Trois disques dynamiques de 20 Gio logiques ; snapshots conservés |
| Services | PostgreSQL 16.15, Python 3.12.3, Django 6.1.1, Gunicorn 23.0.0, Nginx 1.24.0 |
| Réseau | intnet-app ; NAT uniquement sur le proxy, hôte 127.0.0.1:8080 vers proxy :80 |
| Consultation | GET http://127.0.0.1:8080/api/v1/offers/, jeu fictif de quatre offres |

## Résultats

| Grandeur | Médiane retenue |
| --- | ---: |
| Démarrage des trois VM jusqu'au catalogue HTTP 200 | 20.473 s |
| Mémoire hôte : somme RSS des trois processus VirtualBox au repos | 1.454 Gio |
| Disque : taille cumulée des fichiers, snapshots inclus | 10.783 Gio |
| Disque : blocs réellement alloués aux fichiers | 10.755 Gio |
| Latence de consultation : médiane des trois médianes de dix appels | 62.431 ms |

| Série | Démarrage (s) | RSS (Gio) | Fichiers disque (Gio) | Blocs alloués (Gio) | Médiane des dix GET (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 21.095 | 1.454 | 10.712 | 10.684 | 62.431 |
| 2 | 20.473 | 1.451 | 10.783 | 10.755 | 103.480 |
| 3 | 20.372 | 1.461 | 10.818 | 10.790 | 60.898 |

Les octets, les tailles de chaque disque, la mémoire de chaque VM et les trente
latences individuelles sont dans le JSON. Les médianes affichées ici sont
arrondies à trois décimales ; les valeurs brutes restent inchangées.

## Interprétation et limites

Ces chiffres décrivent le poste et la configuration ci-dessus au repos.
Le client HTTP lit la réponse complète et le JSON, sans session ni connexion
persistante. Les VM sont réellement éteintes entre les séries ; le cache disque
hôte n'est pas purgé. Le temps de démarrage inclut les trois commandes startvm,
le démarrage des systèmes et la première consultation réussie de la base via
Django et Nginx.

La RSS est une mesure côté hôte des processus VM ; des pages partagées peuvent
être comptées plusieurs fois et VBoxSVC est exclu. Les 5 Gio configurés aux
invités sont une capacité, distincte de la RSS relevée. L'empreinte disque inclut
l'historique des snapshots des trois clones, et exclut modèle, ISO et OVA ;
elle est distincte des 60 Gio de capacité virtuelle totale.

Une tentative antérieure avec le proxy en default/KVM a échoué sans catalogue
après 240 secondes. La console s'est bloquée pendant le démarrage du noyau.
Cet échec n'entre pas dans les médianes de la nouvelle configuration ; les trois
séries ci-dessus ont toutes été exécutées avec le proxy en minimal. Le
[relevé de l'incident](incident-etape10.txt) et sa
[capture réelle](etape10-demarrage-bloque.png) restent disponibles. La cause
exacte n'a pas été établie ; aucune modification du code applicatif n'a été faite.

Il ne s'agit pas d'une campagne de charge ni d'une comparaison avec les
conteneurs. Cette dernière devra reprendre le même catalogue, la même route et
le même protocole HTTP en documentant les différences de mesure des ressources.
Le temps humain de préparation des machines n'a pas été chronométré.
