# DAMA Lite — affectation physique CAM1–CAM8

## Problème observé le 26 octobre 2026

Les huit UC60 présentent **le même numéro de série** dans leurs
descripteurs USB (\`200901010001\`) : les liens
\`/dev/v4l/by-id/usb-DSJ_UC60_...\` sont alors ambigus et sont
écrasés par le dernier appareil. Ne jamais affecter ces caméras
par \`/dev/video0\` ou \`/dev/v4l/by-id\` ; les chemins
\`/dev/v4l/by-path\` correspondent aux ports physiques du hub.

À 18 h, le Pi avait **quatre webcams distinctes** présentes sur
\`1.2.1\`, \`1.2.2\`, \`1.2.3\`, \`1.2.4\` et quatre absentes
sur le hub droit \`1.1.x\`.

Retour de l'opérateur :

| Ancienne tuile | Vue réellement observée | Port USB actuel |
|---|---|---|
| CAM1 | Caméra physique 3 | 1.2.2 |
| CAM2 | Caméra physique 1 | 1.2.4 |
| CAM3 | Caméra physique 4 | 1.2.1 |
| CAM4 | A semblé montrer CAM1 mais souvent HTTP 503 | 1.2.3 |

## Correspondance appliquée au staging

| Tuile DAMA Lite | Port USB \`1.2.x\` | Validation terrain |
|---|---|---|
| CAM1 | 1.2.4 | Correspond au retour physique CAM1 |
| CAM2 | 1.2.3 | **À CONFIRMER :** quatrième port non encore observé avec succès |
| CAM3 | 1.2.2 | Correspond au retour physique CAM3 |
| CAM4 | 1.2.1 | Correspond au retour physique CAM4 |

Le bug de CAM4 qui répondait HTTP 503 venait du quota logiciel
de **trois flux MJPEG ouverts**, des vues anciennes conservées par
Chromium. Un changement de caméra ferme dorénavant les autres
prévisualisations, avec éviction de secours du flux le moins récent.

CAM5–CAM8 ne sont pas modifiées. Leur hub \`1-1.1\` échoue
au niveau noyau Linux (\`USB err -71\`, descripteur illisible) :
il faut résoudre l'alimentation/câblage avant la qualification.

L'outil \`python -m dama_lite.camera_remap --apply-staging\`
fait une sauvegarde et modifie uniquement \`config.staging.json\`,
sans recopier ni afficher le secret Entra et sans activer la chauffe.
La cohérence des huit chemins est testée avant écriture.

## Vérifications sur le tactile

Après déploiement, ouvrir **CAM1**, **CAM3**, **CAM4** et confirmer que
leurs vues correspondent aux plaques/positions 1, 3 et 4.
Puis ouvrir **CAM2** : cette vue doit maintenant montrer le
périphérique situé sur le port \`1.2.3\`, qui n'avait pas été accessible
à cause des trois flux MJPEG bloquants. **Ne pas déclarer CAM2
physiquement validée sans l'observation de l'opérateur.**

Il faudra également vérifier les huit groupes LED par rapport aux
positions physiques ; le groupe 1=LED1–8, le groupe 8=LED57–64.
