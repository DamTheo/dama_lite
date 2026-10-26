# Sélection de caméra, aperçu de la plaque et fin d'expérience

## Écran Nouvelle analyse

Sur le tactile Raspberry Pi 7" (800×480) :

- Les huit positions restent visibles à gauche dans leur grille 4×2.
- La caméra sélectionnée fournit à droite un **aperçu vidéo MJPEG natif
  640×480, affiché dans un cadre compact** (sans seconde capture PNG).
  Une déconnexion montre une erreur puis une tentative de reconnexion.
- Une position sélectionnée et disponible donne une respiration en
  **vert sur ses 8 LED**, période 2,8 secondes et luminosité globale
  plafonnée à 10 %. Les 7 autres groupes conservent leur état.
- La sélection est envoyée à /api/selection uniquement pendant la page
  Nouvelle analyse. Elle expire côté Pi après quatre secondes sans
  renouvellement pour ne pas laisser clignoter une ancienne position.
- Les défauts **rouges**, les tests **jaunes** et l'extinction pendant
  une photographie scientifique ont priorité sur le repérage.
- Le nom d'expérience obligatoire est repris tel quel pour son **seul
  dossier SharePoint**, directement sous DAMA-Lite, sans dossier caméra.

## Bouton de fin

La page **Analyses en cours** avait déjà un bouton d'arrêt par test.
Le libellé devient « Terminer » et un bouton « Terminer l'expérience »
figure également dans la page de la caméra occupée.

Une confirmation est obligatoire : le backend exécute
\`SessionManager.stop_test(test_id)\`, qui interdit les nouvelles
photographies, enregistre \`state=stopped\` et laisse intactes les
photos déjà présentes dans la file locale et leurs transferts Graph.
La position redevient verte si la caméra reste connectée et
sans défaut. Si une photo est précisément en cours, elle peut
achever son écriture : aucun fichier partiel n'est créé.

La chauffe reste **désactivée** dans le profil staging existant :
le lancement réel d'une expérience reste interdit tant que les
protections thermiques n'ont pas été qualifiées.

## Essais sur le Pi

\`\`\`bash
cd /home/damocles/dama-lite-staging
PYTHONPATH=backend python3 -m dama_lite.selection_smoke --camera 3 --seconds 1.5
sudo journalctl -u dama-lite-led-bridge.service -n 20 --no-pager
\`\`\`

Ce diagnostic ne déclenche ni chauffe, ni session, ni transfert Graph
et efface sa sélection avant de se terminer.
