# Huit webcams UC60 — identité stable des positions

Les liens \`/dev/video0\`, \`/dev/video2\`, etc. changent au redémarrage.
Sur le Pi 4, les liens \`/dev/v4l/by-path/*-usb-*-video-index0\`
identifient le **port physique**, ce qui convient aux huit positions si le
câblage du hub est fixé après qualification.

Le 23 octobre 2026, des caméras UC60 ont été observées sur deux nouveaux ports
USB \`1.2.2\` et \`1.2.4\`; le port antérieurement attribué à CAM1 \`1.2.1\`
n'existait plus. Le code de production doit **refuser de remplacer
silencieusement** cette association pendant une expérience.

## Commandes de staging

\`\`\`bash
cd /home/damocles/dama-lite-staging
PYTHONPATH=backend python3 -m dama_lite.camera_mapping
# Vérifier que les appareils apparaissent sur les positions attendues.
# Les tests et Graph étant encore désactivés, la prochaine commande
# permet d'écrire le mapping dans la configuration de staging seulement :
PYTHONPATH=backend python3 -m dama_lite.camera_mapping --apply
sudo systemctl restart dama-lite-staging.service
\`\`\`

L'application écrit d'abord une sauvegarde datée de \`config.staging.json\`,
puis fait un remplacement atomique avec contrôle des chemins.
**Elle refuse l'appairage si des tests historiques existent, si Microsoft
Graph est actif ou si le staging active un actionneur GPIO.**

Lorsque les huit caméras seront branchées et installées définitivement,
confirmer physiquement chaque position par son aperçu et ses étiquettes,
avant d'activer les analyses. Aucun suivi de caméra par numéro /dev/videoN.
