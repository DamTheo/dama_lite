# DAMA Lite - correction des caméras 1 et 2 (30 octobre 2026)

L'opérateur a constaté que, suite au remappage des huit caméras,
seuls les retours vidéo **CAM1** et **CAM2** étaient encore inversés.

La correction échange uniquement les ports USB 1.1.3 et 1.1.4
et confirme ces deux identités. Aucun câble n'a été déplacé.

| Caméra logique | Chemin physique USB |
|---|---|
| CAM1 | 1.1.4 |
| CAM2 | 1.1.3 |
| CAM3 | 1.1.2 |
| CAM4 | 1.1.1 |
| CAM5 | 1.2.4 |
| CAM6 | 1.2.3 |
| CAM7 | 1.2.2 |
| CAM8 | 1.2.1 |

Les huit chemins restent différents sous /dev/v4l/by-path.
Les numéros /dev/videoX et les liens by-id ne sont pas employés,
car ils ne sont pas fiables pour huit caméras UC60 identiques.

La correction lève le marquage provisoire « À identifier » de CAM2 :
l'opérateur a désormais identifié explicitement l'inversion des
deux dernières sources physiques.

Déploiement : script de remappage atomique conservant une sauvegarde
du fichier config.staging.json. Aucun paramètre de chauffe, LED,
SharePoint, permissions ou arrêt du Pi ne doit être modifié.

Valider ensuite le retour vidéo des caméras 1 et 2 sur le tactile.
La résistance chauffante reste désactivée tant que sa protection
matérielle indépendante n'est pas qualifiée.
