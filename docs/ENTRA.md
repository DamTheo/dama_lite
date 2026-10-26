undefined

## Identifiants déjà déployés (audit du 26 octobre 2026)

Sur Incub-resa, le fichier privé \`/etc/dama-lite/graph.env\` existe, mode
\`0600\`, avec les cinq variables **non vides** :
\`MS_TENANT_ID\`, \`MS_CLIENT_ID\`, \`MS_CLIENT_SECRET\`,
\`MS_DRIVE_ID\`, \`MS_FOLDER_ID\`.

Pour éviter de demander une seconde fois le secret, le backend supporte
désormais dans la section SharePoint du JSON **uniquement le chemin** :

\`\`\`json
{"graph_env_path":"/etc/dama-lite/graph.env"}
\`\`\`

Le logiciel charge en mémoire les identifiants, conserve le secret
exclusivement dans ce fichier privé et **vérifie avant tout POST** que
l'ID de dossier reçu pour le chemin exact \`DAMA-Lite\` correspond à
\`MS_FOLDER_ID\`. Aucune variable secrète n'est ajoutée à Git, au
fichier JSON, à l'URL du navigateur ou aux journaux.

Le contrôle de préproduction \`SharePointClient.verify_read_only()\`
effectue seulement les GET du lecteur \`R&D Biologie\` et du dossier
exact et ne crée ni test, ni photo. Le service staging peut activer
SharePoint indépendamment de la chauffe et des LED.
