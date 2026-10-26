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


## Installation du marqueur après autorisation explicite

Le fichier modèle \`deploy/led-authorization-marker.txt\` contient uniquement
le texte d'autorisation non secret. La seule installation dans
\`/etc/dama-lite/leds-qualified\` se fait avec propriétaire root et
droits 0600, puis le service systemd peut être activé. La présence
du marqueur confirme seulement l'autorisation opérateur et le fait
que le test LED a terminé sans erreur, pas une observation visuelle.

\`\`\`bash
cd /home/damocles/dama-lite-staging
sudo install -o root -g root -m 600 deploy/led-authorization-marker.txt /etc/dama-lite/leds-qualified
sudo systemctl daemon-reload
sudo systemctl enable --now dama-lite-led-bridge.service
\`\`\`

Le relais chauffage GPIO21 et \`dama-lite.service\` restent éteints/inactifs.


## Correctif du 26 octobre 2026 — répertoire de notification lgpio

Lors du premier démarrage réel du pont LED, \`pinctrl get 12\`
a confirmé le mode \`PWM0_0\` et \`systemd\` a confirmé le service actif.
Cependant, le driver a affiché un avertissement
\`xCreatePipe: Can't set permissions ... Read-only file system\`
car il essayait d'ouvrir son canal de notification dans
le dossier Git protégé en lecture seule.

L'unité utilise maintenant le répertoire d'exécution privé
\`/run/dama-lite-led\` (créé par systemd avec les droits 0700),
autorisé en écriture malgré \`ProtectSystem=strict\`.
Le journal affiche le vecteur d'états de chaque groupe seulement
à chaque changement, ce qui permet de contrôler les huit groupes sans
saturer les logs. Le pilote ne touche jamais GPIO21.


## Stabilisation de l'affichage LED (26/10/2026)

Après le lancement du service sur l'appareil, le journal montrait des
alternances \`available ×8\` et \`off ×8\` toutes les quelques secondes,
alors qu'il n'y avait **aucun test en cours ni aucune photo programmée**.
Ceci correspond à des lectures de l'API locale manquées au milieu de
la charge USB (timeout de 0,7 s auparavant).

Le service conserve désormais l'état connu pendant **3 secondes**
maximum lorsqu'une seule requête de statut échoue, puis
**éteint immédiatement tout le bandeau** si cette durée est dépassée.
Les ordres de blackout photo correctement reçus ne bénéficient
d'aucune temporisation et restent immédiats. La fréquence de lecture
est réduite à 2,5 Hz pour limiter la charge du Pi.

\n## Repérage tactile d'un emplacement (nouvelle analyse)\n
Pendant l'écran « Nouvelle analyse », le kiosque envoie la caméra choisie
via `POST /api/selection` à intervalles réguliers. Le backend mémorise
une sélection volatile expirant automatiquement après **4 secondes** ;
aucun enregistrement SQLite ni écriture SharePoint.

Seul le segment physique correspondant (8 LED) est modulé doucement
entre **18 et 100 % du vert déjà limité matériellement à 10 %**,
avec période de 2,8 secondes. Les sept autres segments restent dans leur
état normal. **Une analyse en cours reste jaune ; une panne reste rouge**,
même si cette caméra est sélectionnée. Le noir pendant la photo scientifique
reste prioritaire. Lors du retour au menu ou après lancement, la sélection
est effacée ; un navigateur planté perd sa sélection automatiquement.

Le GPIO21, la chauffe et l'autorisation de démarrer un test ne sont
jamais modifiés par cette fonction.
