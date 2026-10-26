undefined

### Bascule contrôlée vers le fichier existant (sans activer les GPIO)

\`\`\`bash
cd /home/damocles/dama-lite-staging
PYTHONPATH=backend python3 -m dama_lite.graph_setup --configure
sudo systemctl restart dama-lite-staging.service
PYTHONPATH=backend python3 -m dama_lite.graph_setup --verify
\`\`\`

\`--configure\` sauvegarde atomiquement le JSON précédent, refuse tout
changement de GPIO ou remplacement d'identifiants existants et inscrit
seulement \`graph_env_path\`. \`--verify\` effectue les GET distants
nécessaires pour vérifier la bibliothèque et le dossier cible ; **aucun
dossier ni photo n'est créé**. Pour le mode MS_*, le backend utilise
l'endpoint OAuth 2.0 client_credentials directement avec \`requests\`,
en gardant le secret et le jeton en mémoire uniquement. MSAL reste
disponible pour les autres profils d'authentification.
