# CAMÉRAS DAMA Lite — correction du 30 octobre 2026

Huit caméras UC60 sont désormais présentes sur deux hubs USB,
avec des chemins distincts /dev/v4l/by-path (pas by-id, numéros
de série identiques).

La lecture directe des emplacements de l'ancienne interface par
l'opérateur a donné :

| Ancien bouton | Caméra physique observée |
|---|---|
| 1 | 5 |
| 2 | 6 |
| 3 | 7 |
| 4 | 8 |
| 5 | 4 |
| 6 | 3 |
| 7 | 1 |
| 8 | 1 (doublon, physique 2 non identifiée) |

Nouvelle attribution demandée (emplacement = numéro physique) :

| Nouvelle caméra | Ancienne vue | Port stable | Confiance |
|---|---|---|---|
| CAM1 | 7 | 1.1.3 | retour opérateur |
| CAM2 | 8 | 1.1.4 | PROVISOIRE / À VÉRIFIER |
| CAM3 | 6 | 1.1.2 | retour opérateur |
| CAM4 | 5 | 1.1.1 | retour opérateur |
| CAM5 | 1 | 1.2.4 | retour opérateur |
| CAM6 | 2 | 1.2.3 | retour opérateur |
| CAM7 | 3 | 1.2.2 | retour opérateur |
| CAM8 | 4 | 1.2.1 | retour opérateur |

La dernière ancienne vue 8 est supposée correspondre à l'emplacement 2
par élimination, mais cette hypothèse n'est PAS une identification.
Le module écrit mapping_verified=false pour CAM2. L'interface affiche
« À identifier » et la création d'une analyse sur cette caméra est
refusée côté serveur, même après qualification de la chauffe.

Le remappage atomique dans config.staging.json conserve les paramètres
Entra, SharePoint, chauffage GPIO21, bandeau LED GPIO12 et extinction.
Une copie horodatée permet un retour arrière.

Les 8 chemins USB sont indépendants. Une prise physique qui change de port
USB change d'identité : vérifier les numéros après tout recâblage.

Pour confirmer CAM2, regarder son retour et son groupe LED puis signaler
explicitement le bon emplacement physique avant de retirer le verrou.
