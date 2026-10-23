# Installation et qualification — à ne PAS exécuter avant autorisation

Le **staging sécurisé** est désormais installé sur le Pi 4 `192.168.1.201`, avec démarrage automatique vérifié. En revanche, **le service de production commandant la chauffe n'est ni installé ni qualifié**. Les commandes suivantes restent une procédure de bascule future, à ne pas exécuter automatiquement.

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

Prévoir Raspberry Pi OS Debian 12 et Python 3.11. Node.js 22+ peut rester sur PC01 pour construire l'interface, puis transférer `ui/dist` : aucune installation Node n'est requise sur le Pi. Dépendances système : `python3-venv`, `python3-opencv`, `python3-numpy`, `openssl`, `chromium` et bibliothèques GPIO compatibles Pi 4.

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

Le fichier `deploy/dama-lite-kiosk.desktop` est déjà installé sous `~/.config/autostart/` et a été validé après reboot. Réutiliser cette entrée lors de la bascule de production sans créer un second parcours de démarrage.

## Tests hors matériel

\`\`\`bash
cd backend
python3 -m unittest discover -s tests -v
cd ../ui
npm install
npm run build
\`\`\`

Le backend continue de refuser le démarrage d'analyses tant que Microsoft Entra n'est pas configuré (certificat ou secret client dans un fichier privé). Il n'existe **aucun mode simulation produisant de faux dossiers ou de fausses captures**.

## Déploiement et retour arrière

Ne remplacer aucun script de chauffe existant sans identifier son superviseur et son propriétaire. Prévoir un snapshot image système, vérification des capteurs/relais hors charge, activation progressive, et procédure de rollback rétablissant le programme antérieur et ses services **uniquement après retour à l'état thermique sûr**. Tester démarrage à froid, veille du bureau, reconnexion réseau et arrêt au bouton avant utilisation sans surveillance.
