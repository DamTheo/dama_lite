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


## Diagnostic direct du 26 octobre 2026 — huit caméras branchées

La lecture USB a identifié **huit UC60** (VID:PID \`0bda:5805\`) réparties
sur **deux hubs Terminus 1a40:0101**, eux-mêmes connectés à un hub VIA :
- hub \`1-1.1\` : quatre UC60 sur \`1.1.1\` à \`1.1.4\` ;
- hub \`1-1.2\` : quatre UC60 sur \`1.2.1\` à \`1.2.4\`.

Le journal noyau montre le 26/10 des répétitions de \`-71\`,
\`hub_ext_port_status failed\`, la déconnexion du hub \`1-1.1\`
et de ses **quatre UC60**, puis des échecs de reset et des réénumérations.
Ces messages signalent un problème USB de lien ou d'alimentation,
pas une mauvaise valeur de \`/dev/videoN\`.

Le statut \`vcgencmd get_throttled = 0x0\` ne mesure **pas**
l'alimentation locale de chaque hub. Examiner source 5 V du hub,
câbles amont et connecteurs, courant et stabilité de la distribution.
Les webcams ayant un numéro de série USB identique, les liens
\`by-id\` ne doivent pas être utilisés pour assigner les positions.

### Préparer les huit positions même si quatre ports sont hors ligne

Après confirmation de la liste des ports réellement détectés au premier
démarrage, les quatre ports \`1.1.x\` peuvent être **réservés explicitement**
dans le fichier de staging :

\`\`\`bash
cd /home/damocles/dama-lite-staging
PYTHONPATH=backend python3 -m dama_lite.camera_mapping \
  --reserve-offline-ports 1.1.1,1.1.2,1.1.3,1.1.4
# Inspecter le JSON : aucune modification tant que --apply est absent.
PYTHONPATH=backend python3 -m dama_lite.camera_mapping \
  --reserve-offline-ports 1.1.1,1.1.2,1.1.3,1.1.4 --apply
sudo systemctl restart dama-lite-staging.service
\`\`\`

L'opération n'active aucun composant matériel. Les emplacements
correspondants restent signalés **déconnectés** tant que Linux ne peut
pas ouvrir les webcams. Les liens physiques sont conservés :
le retour du hub rétablit leurs emplacements sans réattribuer les tests
aux mauvaises caméras. **La correspondance réelle CAM1–CAM8 avec les
positions physiques de l'incubateur doit encore être contrôlée** avant
toute analyse scientifique.
