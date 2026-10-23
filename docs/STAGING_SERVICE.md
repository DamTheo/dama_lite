# Intégration autonome de DAMA Lite — profil de validation

## Usage prévu

Le profil \`dama-lite-staging.service\` démarre le backend sans aucune
commande de chauffage, LED ou extinction Linux. Sa commande
\`ExecStartPre\` refuse explicitement le démarrage si l'un de ces
actionneurs a été activé dans le fichier \`config.staging.json\`.

La session graphique LightDM de \`damocles\` ouvre automatiquement
\`deploy/dama-lite-kiosk.desktop\` ; son lanceur attend que l'API locale
réponde avant de démarrer Chromium en mode kiosque 800×480.

**Ne pas activer le service de production \`dama-lite.service\` pour ces
tests. Aucun accès Microsoft Entra n'est requis pour afficher l'interface
et visualiser la caméra.**

## Paramètres confirmés

- Luminosité maximale **10 %** pour les 64 NeoPixels (physiquement inactifs
  dans le staging).
- Capteur DS18B20 sur BCM22 ; relais sur BCM21, LED sur BCM12.
- Préparation de l'application Microsoft Entra par l'utilisateur ; aucune
  clé ou certificat dans Git, et aucun envoi réel tant que l'app n'est pas
  configurée et vérifiée.
- Screen DSI 800×480, Chromium présent, LightDM avec autologin déjà actif.
- Le précédent \`~/.config/autostart/camera.desktop\` référence un
  fichier \`/home/damocles/lanceur.sh\` absent. Avant remplacement, en
  conserver une copie locale pour rollback.

## Contrôle et rollback

\`\`\`bash
systemctl status dama-lite-staging.service
curl -fsS http://127.0.0.1:8765/api/status
journalctl -u dama-lite-staging.service --no-pager -n 70
\`\`\`

Pour revenir au bureau d'origine sans chauffer : arrêter puis désactiver
\`dama-lite-staging.service\`, retirer seulement l'entrée
\`~/.config/autostart/dama-lite-kiosk.desktop\`, restaurer au besoin
\`camera.desktop\` depuis son fichier de sauvegarde. Aucune suppression
de la copie source ou des anciennes données n'est nécessaire.

L'installation du service et du kiosque dans l'OS reste distincte de
la simple présence de ces gabarits dans Git. Documenter l'état réellement
atteint et ne pas annoncer un redémarrage testé sans l'avoir effectué.
