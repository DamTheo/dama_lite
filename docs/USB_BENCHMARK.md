# Qualification des huit webcams par l'API

La commande \`PYTHONPATH=backend python3 -m dama_lite.usb_benchmark --seconds 8\`
ouvre simultanément huit flux HTTP MJPEG de l'application **déjà active**
sur \`127.0.0.1:8765\`.

Chaque client compte les images JPEG du multipart, mesure le délai
d'arrivée de la première image, les octets, les FPS moyens et les erreurs
de transfert. Il **ne stocke aucune image** et ne lance pas d'expérience.

Il ne modifie ni chauffe, ni LED, ni boutons d'extinction et n'a besoin
d'aucune autorisation Microsoft Graph. Les essais intensifs seront
réalisés seulement en mode staging, sans tests microbiologiques.

Pour qualifier les huit voies avant la production :

1. Appairer les ports physiques et vérifier les 8 chemins \`by-path\`.
2. Vérifier chaque caméra isolément avec son aperçu.
3. Exécuter 8 flux concurrents pendant 8 secondes.
4. Observer les journaux kernel USB et températures CPU/DS18B20.
5. Tester la priorité de la photo PNG haute résolution et la reprise MJPEG.
6. Laisser ensuite l'incubateur sous observation prolongée,
   avec défaut USB reproductible si possible.

Un HTTP 200 et quelques images pendant une courte fenêtre ne suffisent
pas à valider plusieurs heures de stabilité du hub USB.
