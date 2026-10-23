# Installation et qualification — à ne PAS exécuter avant autorisation

La version GitHub **n'est pas installée** sur le Pi 4 \`192.168.1.201\`. Les commandes ci-dessous constituent une **procédure prévisionnelle** pour la phase ultérieure. Elles ne doivent pas être exécutées automatiquement.

## Conditions préalables obligatoires

1. Sauvegarder et lire le programme actuellement lancé sur \`Incub-resa\`, ses tâches cron, unités systemd, services de session graphique et fichiers de configuration. Identifier exactement qui possède le GPIO21 pour ne pas commander le relais depuis deux programmes simultanément.
2. Vérifier physiquement l'activation active-high / active-low du relais, son contact **normalement ouvert**, le fonctionnement en absence d'alimentation du Pi et l'existence d'un **thermostat/fusible thermique indépendant** adapté aux résistances.
3. Mesurer la courbe d'échauffement de 22 à 37 °C, le dépassement après coupure, les gradients entre 8 positions, et valider les seuils logiciels provisoires (hystérésis +/-0,3 ; défaut enceinte 41 °C ; CPU critique 80 °C).
4. Identifier le **GPIO du bouton physique** et son câblage (vers GND/pull-up) ; vérifier qu'il ne coupe pas directement l'alimentation avant arrêt Linux.
5. Vérifier la référence exacte du Touch Display 7 pouces, la résolution, les périphériques V4L2, la stabilité des symlinks by-path et l'alimentation des hubs USB.
6. Vérifier l'accès à la bibliothèque SharePoint DAMA-Lite avec le certificat déployé, sans publier la clé dans Git.
7. Garder \`heating_enabled=false\`, \`leds_enabled=false\`, \`allow_os_shutdown=false\` pendant toute la validation initiale.

## Préparation système (plus tard, après validation)

Le dépôt est destiné à être placé dans \`/opt/dama-lite\` et sa configuration dans \`/etc/dama-lite/config.json\` ; les données persistantes se trouvent sous \`/var/lib/dama-lite\`.

Prévoir Raspberry Pi OS Debian 12, Python 3.11 et Node.js 22 ou plus récent. Dépendances système : \`python3-venv\`, \`python3-opencv\`, \`python3-numpy\`, \`openssl\`, \`chromium\` et bibliothèques GPIO compatibles Pi 4.

\`\`\`bash
# EXEMPLES - NE PAS LANCER SUR INCUB-RESA AVANT VALIDATION
sudo mkdir -p /opt/dama-lite /etc/dama-lite/secrets /var/lib/dama-lite
sudo chown damocles:damocles /var/lib/dama-lite
python3 -m venv --system-site-packages /opt/dama-lite/.venv
/opt/dama-lite/.venv/bin/python -m pip install -r /opt/dama-lite/backend/requirements.txt
cd /opt/dama-lite/ui
npm install --no-audit --no-fund
npm run build
\`\`\`

Copier \`deploy/config.example.json\` dans \`/etc/dama-lite/config.json\` et personnaliser **après vérifications** : chemin stable de chaque caméra, identifiants Graph, chemins PEM, GPIO bouton, polarité du relais. Les clés privées ne doivent pas entrer dans Git ni dans le répertoire du frontend.

Le service \`deploy/dama-lite.service\` est un **gabarit**, pas une garantie d'accès GPIO. Vérifier notamment l'existence du groupe \`gpio\`, la compatibilité NeoPixel GPIO12 avec les droits non-root, \`NoNewPrivileges\` et \`ProtectSystem\`. Préférer un helper matériel à privilèges restreints plutôt que faire tourner l'API HTTP/SharePoint en root. Ne pas autoriser l'arrêt système au service avant inspection de polkit / logind.

Le fichier \`deploy/dama-lite-kiosk.desktop\` sera installé sous \`~/.config/autostart/\` pour la session graphique de \`damocles\`, avec auto-login configuré et testé. La commande \`chromium\` peut varier selon l'image OS.

## Tests hors matériel

\`\`\`bash
cd backend
python3 -m unittest discover -s tests -v
cd ../ui
npm install
npm run build
\`\`\`

Le backend reste non opérationnel pour les acquisitions si le certificat SharePoint est absent : il n'existe **aucun mode simulation qui produirait de faux dossiers ou de fausses captures**.

## Déploiement et retour arrière

Ne remplacer aucun script de chauffe existant sans identifier son superviseur et son propriétaire. Prévoir un snapshot image système, vérification des capteurs/relais hors charge, activation progressive, et procédure de rollback rétablissant le programme antérieur et ses services **uniquement après retour à l'état thermique sûr**. Tester démarrage à froid, veille du bureau, reconnexion réseau et arrêt au bouton avant utilisation sans surveillance.
