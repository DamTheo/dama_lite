# Retour vidéo DAMA Lite — MJPEG natif (Raspberry Pi 4)

## Problème résolu

Ancienne version : Chromium demandait \`/api/cameras/N/preview\`, le backend
relançait OpenCV, ouvrait \`/dev/video*\`, décodait trois trames HD, réencodait
le JPEG, puis fermait la caméra. Plusieurs secondes par aperçu et conflits
possibles si le navigateur remplaçait le JPEG précédent.

**Version optimisée :** \`/api/cameras/N/stream\` est un flux HTTP MJPEG
\`multipart/x-mixed-replace\`. FFmpeg ouvre **une fois** le périphérique
V4L2 au format **MJPG natif 640×480** et copie ses JPEG sans décodage
ni réencodage, avec un plafonnement d'environ huit images par seconde
dans le code serveur pour préserver la bande passante et l'interface.

- Le worker FFmpeg est un **processus externe isolé**, que l'API ferme
  si la fenêtre est quittée ou si la caméra cesse de répondre.
- Un flux par caméra en même temps : pas d'ouvertures concurrentes d'une
  même webcam. Plusieurs caméras différentes peuvent avoir chacune un flux.
- La capture scientifique continue à passer par un **PNG 1280×720** via
  le processus isolé OpenCV, au départ puis toutes les cinq minutes.
- Lors d'une photographie programmée, la caméra donne la priorité au PNG :
  le flux FFmpeg est fermé et peut reprendre dès que le navigateur se
  reconnecte. Les LED d'état ne sont coupées que pendant cette photographie.
- Les liens physiques \`/dev/v4l/by-path\` sont obligatoires pour éviter
  d'associer les images d'un test à une autre caméra après un reboot.
- Aucun cache d'images scientifiques modifié, aucun sacrifice de la résolution
  des PNG pour accélérer les aperçus.

## Mesures réelles sur Incub-resa

Test de deux flux MJPEG lancés en parallèle, pendant 5 s chacun :

| | Caméra 1 | Caméra 2 |
|---|---:|---:|
| Délai de première réponse | 0,92 s | 0,72 s |
| Images JPEG reçues | 31 | 33 |
| Images/s observées | 6,2 | 6,6 |

La performance peut évoluer lorsque les huit caméras USB seront branchées.
La troisième caméra déclarée branchée par l'utilisateur n'était pas
énumérée dans Linux au moment de cette mesure. Les messages
\`Cannot enable. Maybe the USB cable is bad?\` / \`unable to enumerate USB device\`
répétés pour un port USB indiquent un problème d'énumération matériel à
résoudre avant qu'un logiciel puisse l'afficher.

## Vérification de coexistence avec les photos

Après désactivation temporaire du service de staging (ne pilote ni
chauffage ni LED) :

\`\`\`bash
cd /home/damocles/dama-lite-staging
PYTHONPATH=backend python3 -m dama_lite.camera_smoke \
  --config config.staging.json --slot 1
\`\`\`

Le diagnostic conserve uniquement les durées et la taille du PNG en
mémoire ; aucune image n'est envoyée à SharePoint ni déposée sur disque.
Il vérifie la préemption du flux MJPEG, l'acquisition PNG et la reprise
de l'aperçu. Ne pas lancer pendant une expérience en cours.
