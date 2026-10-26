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


## Gestion des erreurs UVC transitoires (26/10/2026)

Un essai de capture scientifique sur huit webcams a confirmé des PNG 1280×720
valides sur CAM4–CAM8, mais l'ouverture initiale MJPEG de CAM3 a rencontré
une fermeture de flux. Le noyau signale au même moment des réinitialisations
de la cascade USB \`1-1.1\`.

Le contrôleur permet désormais **une seconde tentative explicite**
d'acquisition PNG, espacée de 750 ms après un échec UVC. Il enregistre
toujours **une seule photographie valide** (et son horodatage réel),
sans générer artificiellement une image manquante. Si les deux essais
échouent, le défaut est remonté à la session pour arrêt sûr et diagnostic.

Cette reprise logicielle ne constitue pas une solution aux erreurs physiques
\`err=-71\` : contrôler la qualité des hubs et leur alimentation.


## Correction du 26 octobre 2026 — reconnexions concurrentes et hub fragile

Les journaux applicatifs du Pi montraient une **tempête de HTTP 503**
sur les caméras 1 à 8 lorsque l'utilisateur changeait d'emplacement
ou qu'une image était retardée. La version précédente rejetait tout
deuxième client sur une même caméra, même si Chromium n'avait pas encore
fermé l'ancienne requête. Chaque retry démarrait un nouveau FFmpeg et
rouvrait V4L2, aggravant les dysfonctionnements USB.

Le nouveau \`LivePreviewManager\` :
- **un seul FFmpeg par caméra**, et diffusion des mêmes JPEG à plusieurs
  clients HTTP sans décodage ni réencodage ;
- dernier JPEG conservé temporairement et UVC laissé ouvert jusqu'à
  **2 secondes après le départ du dernier lecteur** ;
- retour au même emplacement quasi immédiat sans réinitialisation
  matérielle si le délai de grâce est respecté ;
- maximum **3 aperçus distincts concurrents** pour ne pas saturer le bus
  USB2 lorsque plusieurs clients graphiques sont ouverts ;
- capture scientifique PNG prioritaire, tuant le worker vidéo avant
  de rouvrir la webcam pour une photo sans changer résolution ni timing ;
- protection contre les processus morts ou bloqués par timeouts et
  suppression correcte des ouvriers devenus inutiles.

Les quatre caméras CAM5–CAM8 sont assignées physiquement aux ports
\`1.1.1\`–\`1.1.4\` du hub **1-1.1 Terminus 1a40:0101**.
Les journaux noyau du 26/10 à 10 h 51–10 h 53 prouvent plusieurs
**déconnexions de ce hub entier**, puis réénumération des quatre UC60.
Cela nécessite également une action sur l'alimentation et les liaisons
physiques du hub, car du code Python ne peut pas garantir la stabilité
d'un hub qui se déconnecte du noyau Linux.

Le banc d'essai logiciel doit être revalidé après déploiement, caméra
par caméra puis sur plusieurs heures. Aucun lancement expérimental
n'est nécessaire pour contrôler ces aperçus.


L'écran tactile applique de plus un **backoff exponentiel**
sur les erreurs réelles de capture MJPEG (1,5 s, 3 s, 6 s, 12 s
maximum) plutôt que de rouvrir indéfiniment un hub qui vient de
redémarrer. Une première image réussie remet le compteur à zéro ;
le changement de caméra aussi. Les autres emplacements restent
accessibles indépendamment, et le bouton « Reconnecter » permet une
reprise manuelle immédiate.


## Fermeture HTTP et erreurs matérielles

Quand FFmpeg s'arrête après l'envoi des en-têtes multipart HTTP 200,
le serveur doit **terminer la connexion proprement**, pas tenter de
réécrire un code HTTP 503 après les JPEG (ce qui corrompt le flux).
Le serveur intercepte désormais explicitement \`LivePreviewError\`
pendant les écritures multipart et journalise le défaut USB.

Le descripteur USB des huit UC60 déclare **MaxPower 500 mA chacune**
(valeur maximale annoncée, **pas la consommation mesurée**).
Les deux hubs Terminus déclarent chacun **MaxPower 100 mA** pour
leur propre fonction hub. La capacité de l'alimentation réelle des
ports aval doit être établie : quatre webcams par hub peuvent entraîner
des besoins en courant élevés et des resets si la distribution est
insuffisante. Le Pi indique \`throttled=0x0\`, ce qui n'exclut pas
une chute de tension localisée dans un hub.


## Suppression des microcoupures logicielles (26/10/2026, V2)

La revue du backend a identifié une perte artificielle d'images :
le worker Python rejetait toute image reçue moins de **120 ms**
après la précédente, quelle que soit la cadence effective du
périphérique. Cela plafonnait le retour à 8,3 images/s ; les essais
précédents montraient effectivement **5–6 images/s**.

Le filtrage est désormais supprimé. Le worker ne conserve que la
**dernière image JPEG complète**, sans file de retard ni fabrication
d'images. Un navigateur plus lent saute naturellement les anciennes
images pour conserver un retour aussi direct que possible.

**Mesures sur Incub-resa après déploiement :**
- CAM1 : 153 trames MJPEG en 6,01 s, soit **25,46 images/s**
- CAM3 : 123 trames MJPEG en 5,01 s, soit **24,55 images/s**

Ces valeurs représentent les parties JPEG reçues dans le flux HTTP,
et non une mesure de la fréquence de décodage du navigateur. La commande
FFmpeg demande un mode à 10 i/s mais les images réellement délivrées
sont plus nombreuses, signe que la demande de fréquence n'est pas
nécessairement appliquée par le périphérique UVC. **Le mode USB
demandé n'a pas été modifié**, pas plus que la capture PNG scientifique.
Le timeout de flux figé est réduit de 7 à 5 secondes.

Attention : \`640×480\` est le mode UVC natif choisi pour garder
l'aperçu léger ; les photos scientifiques sont enregistrées en
\`1280×720\`. L'interface CSS utilise \`object-fit:contain\` et
n'effectue aucun recadrage, mais **l'angle de champ UVC peut différer**
entre ces deux modes. Si la plainte désigne un recadrage et non des
saccades, il faudra qualifier une prévisualisation plein champ 16:9
sans dégrader la stabilité USB du hub secondaire.


## Cadrage du bas de l'image sur le tactile 7" (26 octobre 2026)

Retour utilisateur : vidéo désormais fluide, mais bas de l'image tronqué.

Le CSS plaçait le MJPEG 640x480 comme élément intrinsèque dans une grille
dont la taille verticale est limitée par les 800x480 px de l'écran.
Même avec \`object-fit:contain\`, la taille de la boîte CSS de l'image
pouvait dépasser celle de son parent, tandis que \`overflow:hidden\`
masquait les derniers pixels en bas.

Les deux vues (« Nouvelle analyse » et « Visualiser une caméra »)
affichent maintenant les JPEG avec une image positionnée absolument
dans un cadre flexible de taille bornée :
\`position:absolute; inset:0; width:100%; height:100%; object-fit:contain;
object-position:center\`. La grille n'est plus agrandie par la dimension
intrinsèque de l'image. Si le rapport du JPEG ne correspond pas à celui
du cadre, il y aura des bandes noires plutôt qu'un rognage.

Un script Node sans dépendances vérifie le contrat CSS avant chaque build.
La capture scientifique PNG 1280x720, le flux UVC 640x480, la cadence
d'acquisition et la chauffe sont inchangés.

Limite : cette correction évite la perte de pixels liée au navigateur ;
elle ne restitue pas les informations absentes de l'image UVC source
ou dissimulées par un objet devant la caméra.
