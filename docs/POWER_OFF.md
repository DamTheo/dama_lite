# DAMA Lite : éteindre proprement le Pi depuis l'écran tactile

## Fonctionnement

Le bouton Power du bandeau supérieur reste accessible sur tous les écrans.

- Sans expérience : confirmation simple.
- Avec expériences : affiche nombre, noms et demande une confirmation.
- Un appui matériel prolongé (lorsque configuré) demande également
  confirmation à l'écran si une ou plusieurs analyses sont actives.
- Après confirmation : coupure de la chauffe, fin des expériences
  (\`stopped\`, pas \`fault\`), attente de la capture PNG éventuellement
  en cours, conservation de la file SQLite/PNG et synchronisation Graph
  au prochain allumage pour les fichiers non encore envoyés.
- Animation existante visage → logo, puis extinction système Linux.
- En cas d'erreur avant l'ordre système : erreur visible, chauffe coupée.

Le Raspberry Pi ne doit pas être arrêté pendant une écriture d'image.
Le service Linux possède un délai d'arrêt de 90 secondes pour les
opérations de nettoyage. Les photos non synchronisées ne sont jamais
supprimées lors du shutdown.

## Séparation des privilèges

Le backend HTTP tourne sous \`damocles\`, sans droit root, et n'a
aucune commande libre. Après clôture des opérations, il publie
atomiquement \`/run/dama-lite-poweroff/confirmed\` dans un dossier
éphémère RAM de mode 0700 appartenant à \`damocles\`.

Une unité root spécifique \`dama-lite-poweroff.path\` attend uniquement
ce marqueur ; \`dama-lite-poweroff.service\` efface le marqueur et
exécute exclusivement \`/usr/bin/systemctl poweroff\`. Cette unité
n'exécute **aucun code Python ni script du dépôt Git utilisateur**.

L'accès root au marqueur est validé par le fichier protégé
\`/etc/dama-lite/shutdown-ui-authorized\`, valeur
\`DAMA_LITE_UI_POWER_OFF_AUTHORIZED\`, propriétaire root mode 0644 (marqueur non secret, non modifiable).
L'utilisateur a autorisé explicitement cette nouvelle fonction.
Elle n'autorise **ni chauffage GPIO21 ni modification des LED GPIO12**.

## Installer sans jamais éteindre lors de la validation

\`\`\`bash
cd /home/damocles/dama-lite-staging
sudo install -o root -g root -m 644 deploy/dama-lite-poweroff.service /etc/systemd/system/
sudo install -o root -g root -m 644 deploy/dama-lite-poweroff.path /etc/systemd/system/
sudo install -o root -g root -m 644 deploy/dama-lite-poweroff.tmpfiles /etc/tmpfiles.d/dama-lite-poweroff.conf
sudo install -o root -g root -m 644 deploy/shutdown-ui-authorization.txt /etc/dama-lite/shutdown-ui-authorized
sudo systemd-tmpfiles --create /etc/tmpfiles.d/dama-lite-poweroff.conf
sudo systemctl daemon-reload
sudo systemctl enable --now dama-lite-poweroff.path
systemctl is-active dama-lite-poweroff.path
PYTHONPATH=backend python3 -m dama_lite.poweroff_setup --enable-staging
sudo install -m 644 deploy/dama-lite-staging.service /etc/systemd/system/dama-lite-staging.service
sudo systemctl daemon-reload
sudo systemctl restart dama-lite-staging.service
\`\`\`

Ces opérations **n'envoient aucune demande d'extinction**.
Le marqueur \`/run/dama-lite-poweroff/confirmed\` ne doit jamais
être créé pendant les contrôles automatiques.

Seule une confirmation du bouton tactile ou du bouton physique peut
le créer. Ne pas faire le test complet de \`poweroff\` sans être devant
l'incubateur et pouvoir le rallumer.

## Sécurité et limites

- La chauffe reste volontairement non qualifiée/désactivée dans le staging.
- Le serveur garde l'écoute seulement sur \`127.0.0.1\` ; toute requête
  de shutdown exige JSON avec \`confirm_active_tests\` booléen strict.
- Le démon root ne fait qu'un \`poweroff\`, aucune commande arbitraire.
- Le port USB et le hub 1-1.1 défaillant ne sont pas modifiés.
- Les expériences actives sont marquées \`stopped\` **uniquement après
  confirmation** ; les coupures imprévues les marquent \`interrupted\`.
- Les photos du spool sont sauvegardées sur le Pi et retentées sur
  SharePoint au prochain démarrage : un arrêt ne garantit pas que les
  transferts en attente soient déjà terminés.
