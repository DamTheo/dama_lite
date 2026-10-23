# Microsoft Entra — intégration future (en attente des identifiants)

**Aucun identifiant client ni secret n'est stocké dans Git.**
Le dossier cible est \`R&D Biologie/03_Projets/04_Résazurine/
03_Expérimentations & Résultats/DAMA-Lite/<Nom_test>\`.
Un dossier est créé directement par test, sans dossier par caméra.

## Application Entra

1. Créer une **inscription d'application** dédiée à DAMA Lite,
   en tenant unique.
2. Noter l'**ID de locataire** (\`tenant_id\`) et l'**ID de l'application**
   (\`client_id\`) : ce sont des identifiants, pas des secrets.
3. Choisir **un seul** mode d'authentification :
   - **Recommandé pour équipement long terme** : certificat X.509,
     avec clé privée et certificat public stockés dans le répertoire
     sécurisé du Pi ; renouveler avant expiration.
   - **Alternative** : secret client Entra stocké exclusivement dans
     \`/etc/dama-lite/secrets/entra-client-secret\`, avec chmod 600,
     en local sur le Pi. Le JSON contient seulement
     \`client_secret_path\`, **jamais la valeur du secret**.
4. Configurer le périmètre de permissions Microsoft Graph le plus limité
   possible pour les écritures requises. Privilégier un modèle
   \`Sites.Selected\` avec attribution ciblée au site Intranet et droits
   nécessaires à la création de sous-dossiers et au téléversement. Faire
   confirmer cette politique et les permissions effectives par l'admin
   Microsoft 365 ; une attribution applicative incorrecte provoquera
   des HTTP 403, ce qui doit bloquer l'analyse sans perdre de photos.
5. Renseigner l'ID de la bibliothèque **R&D Biologie** (\`drive_id\`),
   pas celui de OneDrive ou Documents. Le backend vérifie le nom exact
   de la bibliothèque avant de créer un dossier de test.

## Configuration locale (non publiée)

Mode secret : \`/etc/dama-lite/config.json\` doit contenir
les ID non secrets, \`client_secret_path\` vers le fichier de
valeur secrète, \`private_key_path=""\`, \`public_cert_path=""\`.
Mode certificat : fournir les deux chemins PEM et
\`client_secret_path=""\`.

Ne jamais envoyer la valeur d'un secret en message de discussion, dans
un fichier Github ou dans un journal. Si le secret a été exposé,
le révoquer dans Entra et en générer un autre.

## Vérifications avant la première expérience

- Résolution de l'ID de lecteur Microsoft Graph comme **R&D Biologie**.
- Dossier \`DAMA-Lite\` trouvé à son chemin exact.
- Consentement effectif, permissions minimales, authentification.
- Création d'un **dossier test unique** puis téléversement d'une
  image explicitement marquée « vérification » ; contrôle du nom et
  du chemin SharePoint avant passage en production.
- Recherche d'un nom déjà utilisé : l'application doit refuser
  tout doublon, sans renommer l'expérience silencieusement.

Microsoft Entra n'est pas encore configuré sur Incub-resa, ce qui est
normal à ce jalon. Le service \`dama-lite-staging.service\` continue de
fonctionner sans Graph, ni chauffe ni LED.
