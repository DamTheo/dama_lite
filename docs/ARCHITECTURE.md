# Architecture technique DAMA Lite — v0.1

## Sources et périmètre

- **Raspberry Pi 4 B Rev 1.5**, Debian 12 Bookworm, hôte \`Incub-resa\`.
- DS18B20 : identifiant **28-0000006ca681**, overlay \`dtoverlay=w1-gpio,gpiopin=22\`. Relais digitalio BCM21, NeoPixel BCM12 (64 pixels) selon \`Programme_complet.py\`.
- Une caméra UC60 a été observée, ce qui est attendu : les sept autres ne sont pas encore branchées. Chemin persistant observé pour CAM1 dans l'exemple de configuration.
- La source DAMA originale était un simulateur React/TypeScript pour écran circulaire. DAMA Lite n'en reprend que l'identité, le visage, les clignements et le morph d'allumage/extinction. Aucune logique de LLM, AST/CMI, LIMS ou module RJ45 n'est copiée.

## Services

\`\`\`text
SYSTEMD (boot) ─────────────────────┐
                                    ▼
                         backend HTTP 127.0.0.1:8765
                                     │
            ┌────────────────────────┼─────────────────────┐
            ▼                        ▼                     ▼
       thermique                 acquisitions          LED / bouton
       DS18B20 ↔ relay          8 caméras V4L2       8 × 8 NeoPixel
            │                        │                     │
            │                        ▼                     │
            │              SQLite + spool local            │
            │                        │                     │
            │                  Microsoft Graph             │
            │                        │                     │
            └────────────────────────┴─────────────────────┘
                                     ▲
                          UI React plein écran
                           écran tactile 7 pouces
\`\`\`

**Règle :** la vérité des états, les seuils de sécurité, l'autorisation d'analyse et le calendrier des prises de vue appartiennent au backend, jamais à React.

## Thermique

- Échantillonnage DS18B20 à 2 s, CRC obligatoire, détection de la valeur de démarrage non fiable 85 °C.
- Consigne 37 °C, hystérésis initiale +/-0,3 °C (à régler sur essais avec inertie thermique mesurée).
- Lancement si température enceinte >=35 °C, pas de défaut et service thermique actif. Une chute sous 35 °C pendant une expérience est conservée dans les métadonnées temporelles et signalée ; l'acquisition n'est pas supprimée silencieusement.
- Coupure et verrouillage de défaut si sonde en panne ou enceinte >=41 °C **seuil provisoire à valider sur banc**. L'absence de relais ne doit jamais être présentée comme chauffage prêt.
- Alerte CPU >=65 °C, coupure préventive logiciel >=80 °C (seuil provisoire).

## Caméras et temps

- Configuration explicite des **8 emplacements** : chaque \`slot\` désigne un lien stable \`/dev/v4l/by-path/...-video-index0\` ou \`/dev/v4l/by-id/...-video-index0\`.
- Capture et aperçu sont sérialisés par un verrou USB, afin d'éviter des sessions simultanées sur la même webcam et réduire les conflits sur un hub partagé.
- Photo initiale à t=0 puis cible toutes les 300 secondes en fonctionnement ininterrompu. Chaque image reçoit un horodatage UTC réel, une séquence, une température enceinte et une température CPU.
- La cadence de cinq minutes peut dériver si la capture huit caméras dépasse la fenêtre disponible : le banc de qualification doit le mesurer. Pas de génération de photographies fictives pour combler des acquisitions manquées.
- Chaque test sur une caméra est démarré/arrêté indépendamment. Au redémarrage du processus, les tests qui étaient actifs deviennent \`interrupted\` : pas de reprise cachée sans intervention.

## Fichiers SharePoint

Destination **directe** sous le dossier préexistant :

\`\`\`text
DAMA-Lite/
  Test_Ecoli_01/
    20261023_143000_000_t0000min_n0000.png
    20261023_143500_000_t0005min_n0001.png
  Test_Staph_02/
    20261023_151000_000_t0000min_n0000.png
\`\`\`

- Aucun répertoire intermédiaire de caméra ni de date.
- Microsoft Graph crée le dossier avec l'exact nom saisi ; un doublon est rejeté avant d'engager la manipulation.
- Authentification par certificat, secrets hors dépôt.
- Chaque PNG est écrit atomiquement dans une **file locale persistante**, supprimé localement seulement après confirmation du serveur et validation du statut en base. Les échecs réseau sont réessayés avec temporisation. Lorsque la file atteint son quota, l'expérience concernée passe en défaut plutôt que de perdre silencieusement des images.
- SQLite WAL conserve l'état, les erreurs, les noms, la caméra et la file d'envoi ; le serveur ne contient aucun moteur scientifique d'interprétation des images.

## Allumage/extinction

- La régulation et le serveur sont démarrés par \`dama-lite.service\` au boot.
- Le bureau lance Chromium en mode kiosque vers l'API locale pour servir \`ui/dist\`.
- Le maintien du bouton d'extinction (GPIO à identifier) demande : coupure relais -> interruption tracée des analyses -> morph visage→logo -> \`systemctl poweroff\` si autorisé. Les images non synchronisées restent dans la file locale.
- Si l'UI est bloquée, l'arrêt du chauffage ne doit pas attendre l'animation. Si le Pi s'éteint brutalement, seul un dispositif thermique matériel peut garantir la sécurité en cas de relais collé.

## Invariants / non-objectifs

- **Le code ne garantit pas une température homogène** entre les huit positions : la validation expérimentale de gradients et des temps de retour est indispensable.
- **Le CPU ne mesure pas la température des résistances** et son alerte ne constitue pas une protection thermique de l'enceinte.
- Pas de lecture automatique de la couleur ou d'AST/CMI : seules des séries de PNG bruts sont produites.
- Une seule caméra branchée actuellement ; ne pas prétendre que les huit captures ont été vérifiées sur machine.

## Luminosité LED plafonnée

**Décision du 23/10/2026 : luminosité maximale à 10 %** pour les 64 NeoPixels sur BCM GPIO12. Le réglage logiciel reste à `0.10` par défaut ; toute valeur supérieure est rejetée à la lecture de configuration et à l'initialisation du contrôleur. L'extinction des 64 LED pendant les captures est maintenue.

## Tolérance aux défauts CRC 1-Wire (vérification sur Pi)

Un défaut CRC transitoire de la sonde DS18B20 a été observé sur `Incub-resa`, alors que des lectures valides ont suivi. Le driver réessaie désormais jusqu'à **3 lectures espacées de 250 ms**. Aucune ancienne température n'est réutilisée comme mesure courante : **si les 3 lectures sont invalides, l'erreur est transmise et le relais est coupé et verrouillé**. Cette tolérance ne remplace pas la recherche d'une source électrique de CRC NO, ni la protection thermique matérielle indépendante.
