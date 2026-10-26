# Pilotage réel des 64 LED — procédure indépendante du chauffage

Le backend normal, lancé sous \`damocles\`, ne doit pas être exécuté
en root pour accéder à la bibliothèque NeoPixel de bas niveau.

La solution utilise le même \`LightController\` de DAMA Lite, mais
dans un **service distinct et minimal contrôlant uniquement GPIO12**.
Aucun accès GPIO21, à la chauffe ou aux identifiants Microsoft.

## Qualification physique obligatoire (avant activation durable)

- Vérifier présence alimentation du bandeau et masse commune avec Pi.
- Vérifier direction et niveau logique du signal de données GPIO12.
- Vérifier consommation et section des fils ; les 64 LED restent
  limitées à **10 % de luminosité** par code.
- Arrêter le script historique \`Test_LED.py\` si actif. Ne jamais
  piloter GPIO12 depuis deux programmes en parallèle.
- Depuis l'incubateur, réaliser un test ponctuel de quelques secondes,
  à luminosité maximale **0,10** :
  \`cd /home/damocles/dama-lite-staging && sudo env PYTHONPATH=backend python3 -m dama_lite.led_bridge --selftest\`.
  Chaque groupe de huit LED s'allume brièvement en vert, puis s'éteint.
  Aucune résistance n'est actionnée.
- Confirmer visuellement l'ordre réel des huit positions et noter les
  éventuels segments inversés ; corriger l'ordre si nécessaire.

Après qualification, un administrateur peut créer sous contrôle local
\`/etc/dama-lite/leds-qualified\` contenant exclusivement
\`LED_GPIO12_64_10PCT_OPERATOR_AUTHORIZED\`, possédé par root et non modifiable
par d'autres utilisateurs, puis installer et activer le service
\`deploy/dama-lite-led-bridge.service\`. Le démarrage est refusé sans
cette preuve de qualification, et le service n'est pas activé par défaut.

## Couleurs et extinction lors des photos

L'API DAMA Lite locale fournit \`cameras[].health\`, le défaut thermique
global et \`led_blackout\`. Le helper interroge l'API à 5 Hz :

- Vert : caméra branchée et sans défaut de session (indépendamment
  du droit de démarrer un test tant que la chauffe n'est pas prête)
- Jaune : analyse en cours sur cette position
- Rouge : caméra absente/en panne, transfert problématique, ou défaut
  thermique global
- Éteint : position non configurée, API indisponible, arrêt système
  ou période de photographie PNG

Si la communication avec l'API cesse, le helper éteint le bandeau.
Le backend impose toujours le verrouillage du chauffage et le seuil
de 35 °C ; les LED vertes ne valent pas autorisation de lancer un test.


## Autorisation du 26/10/2026 et état de validation

L'utilisateur a autorisé expressément l'activation des LED, tout en
demandant que **la chauffe reste désactivée**. Le programme de test matériel
\`dama_lite.led_bridge --selftest\` a terminé avec code 0 sur
\`Incub-resa\` et a envoyé un ordre d'extinction à la fin du test.

Le marqueur \`leds-qualified\` est désormais une **autorisation opérateur**,
non une certification physique du bandeau. L'ordre et la couleur
des groupes n'ont pas encore été observés directement avec une image.
Après activation permanente, l'utilisateur devra confirmer visuellement
l'ordre des huit segments et l'intensité. Aucun pilote ne doit réclamer
GPIO21, et le service chauffe de production ne doit pas être démarré.
