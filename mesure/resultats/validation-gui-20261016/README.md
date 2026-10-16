# Essais réels JMeter GUI — 16 octobre 2026

Le plan a été exécuté dans JMeter 5.6.3, piloté par ses actions Swing, contre les trois services Docker Engine réels sur le port 8081. Des copies dédiées du plan évitent que son autosauvegarde GUI modifie le plan canonique.

- `reussite.jtl` : trois réponses HTTP 200, aucune erreur.
- `echec.jtl` : CSRF HTTP 200 puis connexion HTTP 401 attendue ; arrêt avant la consultation des candidatures.
- `reussite.png` et `echec.png` : captures du rendu Swing des fenêtres réellement exécutées. La capture du bureau par Robot renvoyait une image noire sous Wayland ; ces images noires sont écartées.
- `verification.json` : assertions et empreintes du plan et des comptes.

Ces essais fonctionnels GUI ne sont pas des mesures de charge. Les mots de passe et les données sont fictifs.
