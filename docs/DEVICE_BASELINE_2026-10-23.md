# Incub-resa — état de référence matériel et logiciel (23/10/2026)

**Machine** : Raspberry Pi 4 Model B Rev 1.5, 4 Go de RAM, Debian 12
Bookworm, Python 3.11.2, Chromium, LightDM actif. Environ 18 Go libres
sur la carte système de 29 Go. Node/npm non installés sur le Pi.

## Observations directes (SSH depuis PC01)

| Élément | Lecture |
|---|---|
| Hostname | Incub-resa |
| Écran connecté | DSI-1, **800×480** (écran tactile rectangulaire 7 pouces) |
| Interface rétroéclairage | 10-0045 |
| DS18B20 | 28-0000006ca681, overlay \`w1-gpio,gpiopin=22\` |
| Enceinte, échantillon de lecture | 22,375 °C (pas une mesure de régulation à 37 °C) |
| CPU, échantillon de lecture | 42,842 °C |
| Synchronisation de l'horloge | NTP=yes |
| Caméras branchées au premier audit | 1 UC60 USB ; une deuxième a été branchée ultérieurement |
| Caméra UC60 — liaison stable | \`/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.2.1:1.0-video-index0\` |
| UC60 — formats annoncés | MJPEG dont 1280×720, 3264×2448 ; YUYV également |
| GPIO12 (LED), GPIO21 (relais) au moment de l'audit | Entrées, pulldown ; **n'établit pas la polarité ni la sécurité électrique du relais** |
| Scripts historiques GPIO actifs détectés | Aucun à l'instant de l'audit ; pas de garantie sur la configuration de redémarrage |
| pigpiod | Inactif |
| API/serveur DAMA Lite préexistant | Non trouvé |

## Tests DAMA Lite réellement exécutés

- Code GitHub cloné isolément dans
  \`/home/damocles/dama-lite-staging\`. Les anciens scripts
  \`Programme_complet.py\`, \`Programme.py\`, \`Test_LED.py\`
  n'ont pas été modifiés.
- Frontend React construit sur PC01 avec Node 24.17.0/npm 11.13.0,
  puis fichiers \`ui/dist\` transférés dans le répertoire de staging.
  **Aucune installation Node sur le Pi**.
- Profil local \`config.staging.json\` dans la copie du Pi :
  \`heating_enabled=false\`, \`leds_enabled=false\`,
  \`allow_os_shutdown=false\`. Les identifiants Graph sont absents.
- Démarrage temporaire du serveur Python \`127.0.0.1:8765\`,
  uniquement pour essais, puis extinction du processus.
- **HTTP 200** sur \`GET /api/status\`, affichant
  \`heater_on=false\`, \`ready=false\` (température basse et chauffe désactivée),
  1 caméra raccordée, 0 test, SharePoint non configuré.
- **HTTP 200** sur \`GET /\` avec \`index.html\` et ressources Vite.
- Premier essai d'aperçu vidéo pendant une fermeture temporisée :
  arrêt anormal natif d'OpenCV (\`terminate called without an active exception\`).
  **Correction publiée** : capture isolée dans un processus fils à timeout,
  indépendant du contrôleur thermique.
- Nouvel essai d'aperçu UC60 après correction :
  **HTTP 200** sur \`GET /api/cameras/1/preview\`.
  Le serveur a consigné la requête puis le signal normal de fermeture
  du test. Une validation d'endurance reste nécessaire.
- GitHub Actions : compilation Python, tests unitaires et build UI
  réussis sur les versions publiées jusqu'à ce jalon.

## Prochaine bascule (non effectuée)

**Aucun service de production actif. Un service STAGING systemd et un kiosque autostart sont maintenant actifs et vérifiés après un reboot. Le chauffage et les LED physiques sont désactivés. Aucun fichier envoyé par DAMA Lite à SharePoint à ce stade.**

Avant d'autoriser \`heating_enabled=true\` :

1. Vérifier physiquement la polarité ON/OFF du relais GPIO21,
   la perte d'alimentation, le chemin de puissance des résistances et
   l'existence d'un coupe-circuit/thermostat thermique indépendant.
2. Identifier le véritable bouton physique d'extinction :
   GPIO momentané, événement système ou interrupteur d'alimentation.
   Un coupe-circuit direct ne permet pas une animation logicielle.
3. Mesurer la réponse thermique : hystérésis +/-0,3 °C et limite
   enceinte 41 °C sont des **valeurs initiales provisoires**, non qualifiées.
4. Associer les autres caméras à des chemins USB persistants et valider
   la photométrie, les hubs et l'éclairage.
5. Provisionner une application Graph autorisée, des certificats
   localisés hors Git et l'identifiant exact de la bibliothèque
   **R&D Biologie**. Valider une création de dossier
   \`DAMA-Lite/<Nom_Test>\` puis un upload réel.
6. Vérifier les droits Linux permettant GPIO12 (NeoPixel) sous
   le compte de service, avant d'installer/activer \`dama-lite.service\`.
7. Configurer le kiosque au démarrage uniquement une fois l'installation
   thermique et la procédure d'arrêt vérifiées.

La reprise automatique des analyses n'est pas autorisée après une coupure :
les séries interrompues sont conservées comme \`interrupted\`, avec les
photos mises en attente de transfert.

**Principe** : logiciel en développement ≠ qualification de sécurité
thermique ≠ validation scientifique des incubations.

## Addendum — mise en service sécurisée (23/10/2026)

- `dama-lite-staging.service` : **enabled** et **active**, compte `damocles`, garde `ExecStartPre` refusant chauffage, LED, bouton et extinction OS dans ce profil.
- LightDM autologin et navigateur Chromium `--kiosk` vérifiés après un reboot complet ; capture écran réelle **800×480** contrôlée ; lancement ancien `camera.desktop` sauvegardé et désactivé (lanceur absent).
- GPIO 12 et GPIO 21 conservés en entrée (aucun actionneur commandé). Sonde DS18B20 lue via le noyau Linux.
- CRC 1-Wire transitoire observé ; trois lectures espacées de 250 ms avant de considérer une mesure définitivement invalide ; **relais coupé et défaut verrouillé** si elles échouent, sans réutilisation de température périmée.
- Deux webcams UC60 reconnues sur ports USB physiques `1.2.2` et `1.2.4`. Appairage de staging effectué explicitement avec sauvegarde de la configuration ; aperçus HTTP 200 pour CAM1 et CAM2.
- Le rafraîchissement HTML n'annule plus la photo précédente, les sockets HTTP sont fermées par réponse et le redémarrage du service est de nouveau rapide.
- Microsoft Entra reste en attente ; authentification future par certificat ou secret client conservé dans un fichier privé du Pi, jamais dans Git.
